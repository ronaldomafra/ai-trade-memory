"""Read-only wall-clock observation of paper sessions; never supervises or stops engines."""

import asyncio
import signal
from contextlib import suppress
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from poc.adapters.outbound.files import FileExporter, atomic_write
from poc.adapters.outbound.runtime import DockerRuntime
from poc.adapters.outbound.session_view import SessionViews
from poc.application.sessions import valid_run_id
from poc.config import Config
from poc.domain.primitives import DomainError, canonical_json, iso, utc


def sample_session(views: SessionViews, run_id: str, now: datetime | None = None) -> dict:
    db = views.database(run_id, readonly=True)
    try:
        db.connection.execute("BEGIN")
        snapshot = FileExporter(db).dashboard()
        if snapshot["fixture"]:
            raise DomainError("Operational observation rejects fixture sessions")
        audit = db.audit()
        duplicates = db.connection.execute(
            "SELECT COUNT(*) FROM (SELECT d.portfolio_id,c.candle_open_time,COUNT(*) AS n "
            "FROM decisions d JOIN decision_cycles c ON c.cycle_id=d.cycle_id "
            "GROUP BY d.portfolio_id,c.candle_open_time HAVING n>1)"
        ).fetchone()[0]
        future_memory = db.connection.execute(
            "SELECT COUNT(*) FROM decisions d,json_tree(d.memory_json) j "
            "WHERE j.key IN ('max_matured_at','source_max_available_at') "
            "AND j.value>=d.decision_started_at"
        ).fetchone()[0]
        quote_order = db.connection.execute(
            "SELECT COUNT(*) FROM paper_fills f JOIN paper_orders o ON o.order_id=f.order_id "
            "JOIN decisions d ON d.decision_id=o.decision_id "
            "JOIN price_quotes q ON q.quote_id=f.quote_id WHERE q.observed_at<=d.decision_at"
        ).fetchone()[0]
        initial_valid = len(snapshot["portfolios"]) == 3 and all(
            Decimal(p["initial_usdt"]) == 100 for p in snapshot["portfolios"]
        )
        # The database snapshot may be newer than the start of a multi-session frame.
        # Measure age after reading it; genuine future source clocks still fail closed.
        now = now or datetime.now(UTC)
        stamp = snapshot["market"]["quote_observed_at"]
        quote_age = (utc(now) - utc(stamp)).total_seconds() if stamp else None
        health = snapshot.get("health") or {}
        heartbeat = health.get("last_heartbeat")
        heartbeat_age = (utc(now) - utc(heartbeat)).total_seconds() if heartbeat else None
        freshness_limit = db.run()["config"]["app"]["max_quote_age_seconds"]
        feed_healthy = (
            quote_age is not None
            and 0 <= quote_age <= freshness_limit
            and heartbeat_age is not None
            and 0 <= heartbeat_age <= 120
            and health.get("status") == "RUNNING"
            and health.get("clock_status") == "VERIFIED"
        )
        source_states = db.runtime_state("external_sources") or {}
        external = snapshot.get("external_context") or {}
        return {
            "run_id": run_id,
            "assessed_at": iso(now),
            "symbol": snapshot["market"]["symbol"],
            "fixture": False,
            "event_watermark": snapshot["event_watermark"],
            "audit": audit,
            "invariants_ok": audit["ok"]
            and initial_valid
            and not duplicates
            and not future_memory
            and not quote_order,
            "duplicate_decisions": duplicates,
            "future_memory_items": future_memory,
            "invalid_decision_fill_quote_order": quote_order,
            "initial_capital_valid": initial_valid,
            "quote_age_seconds": quote_age,
            "heartbeat_age_seconds": heartbeat_age,
            "feed_healthy": feed_healthy,
            "health": snapshot["health"],
            "portfolios": snapshot["portfolios"],
            "ai_cost": snapshot["ai_cost"],
            "learning": snapshot["learning"],
            "external_coverage": {
                section: {
                    "status": external.get(section, {}).get("status", "unavailable"),
                    "coverage": external.get(section, {}).get("coverage", "UNAVAILABLE"),
                    "usable_factor_count": len(external.get(section, {}).get("items", [])),
                    "factor_ids": [
                        item["factor_id"] for item in external.get(section, {}).get("items", [])
                    ],
                    "candidate_count": external.get(section, {}).get("candidate_count", 0),
                    "pending_count": external.get(section, {}).get(
                        "pending_count", len(external.get(section, {}).get("pending", []))
                    ),
                    "scope": external.get(section, {}).get(
                        "scope", external.get(section, {}).get("discovery", {}).get("scope")
                    ),
                }
                for section in ("news", "prediction_markets")
            },
            "source_statuses": {
                key: {
                    k: value
                    for k, value in state.items()
                    if k in ("status", "reason", "observed_at")
                }
                for key, state in source_states.get("sources", {}).items()
            },
        }
    finally:
        db.close()


async def observe(
    config: Config,
    run_ids: list[str],
    output: Path,
    duration_hours: float = 24,
    poll_seconds: int = 60,
) -> dict:
    if not 0 < duration_hours <= 168 or not 1 <= poll_seconds <= 3600 or not run_ids:
        raise DomainError("Observation needs sessions, 0–168 hours and 1–3600 second sampling")
    for run in run_ids:
        valid_run_id(run)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "observation.json"
    if manifest_path.exists():
        raise DomainError("Use a new observation directory; prior evidence is never overwritten")
    start_time = datetime.now(UTC)
    previous_frame_at = None
    max_sample_gap_seconds = max(120, poll_seconds * 2)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(signum, stop.set)
            installed.append(signum)
    runtime = DockerRuntime(Path(config.app.data_dir))
    views = SessionViews(config)
    checks, failures, unavailable, degraded = 0, 0, 0, 0
    manifest = {
        "started_at": iso(start_time),
        "required_wall_clock_hours": duration_hours,
        "poll_seconds": poll_seconds,
        "max_sample_gap_seconds": max_sample_gap_seconds,
        "run_ids": sorted(set(run_ids)),
        "mode": "PAPER_OBSERVATION_READ_ONLY",
        "state": "RUNNING",
        "limits": [
            "Source/model validity must be assessed separately from accounting invariants.",
            "COMPLETED means elapsed wall time; acceptance requires reviewing all samples.",
            "A sampling gap or backward clock interrupts the observation; engines keep running.",
        ],
    }
    try:
        while not stop.is_set():
            now = datetime.now(UTC)
            samples = []
            for run in manifest["run_ids"]:
                try:
                    sample = sample_session(views, run)
                    state = await runtime.inspect(run)
                    sample["runtime"] = {
                        key: value
                        for key, value in (state or {}).items()
                        if key in ("running", "status", "image_id", "health")
                    }
                    failures += not sample["invariants_ok"]
                    degraded += not sample["feed_healthy"] or not (state or {}).get("running")
                except Exception as error:
                    sample = {
                        "run_id": run,
                        "status": "UNAVAILABLE",
                        "error_type": type(error).__name__,
                    }
                    unavailable += 1
                samples.append(sample)
            # CLOCK_MONOTONIC excludes Linux suspend time. Compare real UTC frame
            # times so suspension cannot silently turn into a successful 24h run.
            elapsed = max(0, (now - start_time).total_seconds())
            gap_seconds = (now - previous_frame_at).total_seconds() if previous_frame_at else None
            interrupted = gap_seconds is not None and (
                gap_seconds < 0 or gap_seconds > max_sample_gap_seconds
            )
            frame = {"checked_at": iso(now), "elapsed_seconds": elapsed, "sessions": samples}
            if interrupted:
                manifest["interruption"] = {
                    "reason": "CLOCK_MOVED_BACKWARD" if gap_seconds < 0 else "SAMPLING_GAP",
                    "previous_frame_at": iso(previous_frame_at),
                    "resumed_at": iso(now),
                    "gap_seconds": gap_seconds,
                }
                manifest["state"] = "INTERRUPTED"
            previous_frame_at = now
            with (output / "samples.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(canonical_json(frame) + "\n")
                stream.flush()
            checks += 1
            manifest.update(
                {
                    "latest_at": iso(now),
                    "elapsed_seconds": elapsed,
                    "sample_frames": checks,
                    "invariant_failure_samples": failures,
                    "unavailable_samples": unavailable,
                    "degraded_feed_runtime_samples": degraded,
                    "latest": frame,
                }
            )
            if not interrupted and elapsed >= duration_hours * 3600:
                manifest["state"] = "COMPLETED"
            atomic_write(manifest_path, canonical_json(manifest) + "\n")
            if manifest["state"] in ("COMPLETED", "INTERRUPTED"):
                break
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=min(poll_seconds, duration_hours * 3600 - elapsed)
                )
            except TimeoutError:
                pass
        if stop.is_set():
            manifest["state"] = "INTERRUPTED"
            atomic_write(manifest_path, canonical_json(manifest) + "\n")
        return {key: value for key, value in manifest.items() if key != "latest"}
    finally:
        for signum in installed:
            loop.remove_signal_handler(signum)
