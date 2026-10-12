"""Automatic publication and prospective foreign-asset memory, separate from local counts."""

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from poc.application.learning import LearningEngine, learning_protocol
from poc.config import Config
from poc.domain.features import rsi_bucket, volume_bucket
from poc.domain.learning import statistics
from poc.domain.primitives import DomainError, canonical_json, decimal, iso, stable_id, utc
from poc.domain.transfer import balanced_sources, brier_gate, normalize_features


class CatalogPort(Protocol):
    def missing_publications(self, identities: list[str]) -> set[str]: ...
    def publish(
        self, publication_id: str, core: dict, origin: dict, publisher: str, now: datetime
    ): ...
    def sources(self, target_symbol: str, protocol_hash: str, cutoff: datetime) -> list[dict]: ...


class TransferStore(Protocol):
    def published_identities(self) -> list[str]: ...
    def requeue_publications(self, identities: set[str]): ...
    def unpublished_learning_records(self, cutoff: datetime) -> list[dict]: ...
    def run(self) -> dict: ...
    def transaction(self): ...
    def learning_records(self, cutoff: datetime | None = None) -> list[dict]: ...
    def queue_publication(self, publication_id: str, payload: dict, now: datetime): ...
    def pending_publications(self) -> list[dict]: ...
    def acknowledge_publication(self, publication_id: str, now: datetime): ...
    def save_transfer_shadow(self, record: dict): ...
    def score_transfer_shadows(self, now: datetime) -> int: ...
    def transfer_shadows(self, group: str) -> list[dict]: ...
    def transfer_state(self, group: str) -> dict | None: ...
    def set_transfer_state(self, group: str, state: str, detail: dict, now: datetime): ...


class TransferEngine:
    def __init__(
        self, config: Config, local: LearningEngine, store: TransferStore, catalog: CatalogPort
    ):
        self.config, self.local, self.store, self.catalog = config, local, store, catalog
        self.protocol = learning_protocol(config)
        self.last_publication_error = None
        self.publications_reconciled = False

    def register(self) -> int:
        return self.local.register()

    def mature(self, now: datetime) -> int:
        count = self.local.mature(now)
        with self.store.transaction():
            self.store.score_transfer_shadows(now)
        if self.config.learning.transfer.enabled:
            try:
                self.publish(now)
                self.last_publication_error = None
            except Exception as error:
                self.last_publication_error = type(error).__name__
        return count

    def publish(self, now: datetime) -> int:
        if not self.publications_reconciled:
            missing = self.catalog.missing_publications(self.store.published_identities())
            with self.store.transaction():
                self.store.requeue_publications(missing)
            self.publications_reconciled = True
        run = self.store.run()["run_id"]
        records = self.store.unpublished_learning_records(now)
        with self.store.transaction():
            for record in records:
                core = record["core"]
                if core["fixture"]:
                    continue
                for origin in record["origins"]:
                    identity = stable_id(
                        "catalog-publication", run, core["sample_id"], origin["origin_id"]
                    )
                    self.store.queue_publication(
                        identity, {"core": core, "origin": origin, "publisher": run}, now
                    )
        sent = 0
        for row in self.store.pending_publications():
            payload = row["payload"]
            self.catalog.publish(
                row["publication_id"], payload["core"], payload["origin"], payload["publisher"], now
            )
            with self.store.transaction():
                self.store.acknowledge_publication(row["publication_id"], now)
            sent += 1
        return sent

    def feedback(self, state: dict, cutoff: datetime, cycle_id: str | None = None) -> dict:
        local = self.local.feedback(state, cutoff)
        transfer = []
        diagnostics = []
        if not self.config.learning.enabled or not self.config.learning.transfer.enabled:
            return {**local, "transfer": {"state": "DISABLED", "policy_version": "transfer_v1"}}
        try:
            if utc(state["market"]["as_of"]) > utc(cutoff):
                raise DomainError("Future target features cannot be used for transfer")
            normalize_features(state["market"])  # Verify the target relative feature protocol.
            records = self.catalog.sources(state["symbol"], self.protocol, cutoff)
            for horizon in self.config.learning.evaluation_horizons_bars:
                diagnostic, pattern = self._pattern(
                    state, local, records, horizon, cutoff, cycle_id
                )
                diagnostics.append(diagnostic)
                if pattern:
                    transfer.append(pattern)
        except Exception as error:
            diagnostics = [{"state": "UNAVAILABLE", "reason": type(error).__name__}]
            transfer = []
            for horizon in self.config.learning.evaluation_horizons_bars:
                try:
                    _, _, group, _, _ = self._identity(state, horizon)
                    with self.store.transaction():
                        self.store.set_transfer_state(group, "UNAVAILABLE", diagnostics[0], cutoff)
                except Exception:
                    # A missing/invalid target context has no trustworthy group identity.
                    continue
        local_patterns = local.get("patterns", [])
        composed = list(local_patterns)
        local_keys = {
            (row["position_context"], row["label_kind"], row["horizon_bars"], row["market_regime"])
            for row in local_patterns
        }
        for pattern in transfer:
            key = tuple(
                pattern[field]
                for field in ("position_context", "label_kind", "horizon_bars", "market_regime")
            )
            if key not in local_keys and len(composed) < self.config.learning.max_memory_items:
                composed.append(pattern)
        return {
            **local,
            "status": "available" if composed else local["status"],
            "patterns": composed,
            "transfer": {
                "policy_version": "transfer_v1",
                "normalizer_version": "relative_features_v1",
                "groups": diagnostics,
                "publication_error": self.last_publication_error,
            },
        }

    def _identity(self, state: dict, horizon: int):
        market = state["market"]
        holding = state["portfolio"]["has_position"]
        key = {
            "position_context": "holding" if holding else "flat",
            "label_kind": "HOLD_VS_SELL_RETURN" if holding else "ENTRY_LONG_NET_RETURN",
            "horizon_bars": horizon,
            "market_regime": market["market_regime"],
            "rsi_bucket": rsi_bucket(market["rsi_14"]),
            "volume_bucket": volume_bucket(market["volume_ratio"]),
            "volatility_bucket": market["volatility_bucket"],
        }
        run = self.store.run()["run_id"]
        group = stable_id(
            run, state["symbol"], self.protocol, "transfer_v1", "relative_features_v1", key
        )
        validation_key = {
            field: key[field]
            for field in ("position_context", "label_kind", "horizon_bars", "market_regime")
        }
        validation_group = stable_id(
            run,
            state["symbol"],
            self.protocol,
            "transfer_v1",
            "relative_features_v1",
            validation_key,
        )
        return key, run, group, validation_key, validation_group

    def _pattern(
        self,
        state: dict,
        local: dict,
        records: list[dict],
        horizon: int,
        cutoff: datetime,
        cycle_id: str | None,
    ):
        key, run, group, validation_key, validation_group = self._identity(state, horizon)
        matching = [
            row
            for row in records
            if all(row["core"].get(field) == value for field, value in key.items())
        ]
        neutral = sum(decimal(row["core"]["return_pct"]) == 0 for row in matching)
        selected = balanced_sources(matching, self.config.learning.transfer.max_source_samples)
        prior = self.store.transfer_state(group)
        was_active = prior is not None and prior["state"] in ("ACTIVE", "SUSPENDED")
        minimum = self.config.learning.transfer.min_source_samples
        details = {
            **key,
            "source_group": group,
            "validation_group": validation_group,
            "source_sample_count": len(selected),
            "neutral_source_examples": neutral,
            "target_symbol": state["symbol"],
            "source_cutoff_at": iso(cutoff),
        }
        if len(selected) < minimum:
            status = (
                "SUSPENDED"
                if was_active
                else "NO_SOURCES"
                if not records
                else "INSUFFICIENT_SOURCE"
            )
            details.update({"state": status, "reason": "INSUFFICIENT_COMPATIBLE_FOREIGN_EXAMPLES"})
            with self.store.transaction():
                self.store.set_transfer_state(group, status, details, cutoff)
            return details, None
        wins = sum(decimal(row["core"]["return_pct"]) > 0 for row in selected)
        p = Decimal(wins + 1) / Decimal(len(selected) + 2)
        baseline = next(
            (
                Decimal(str(pattern["smoothed_win_rate"]))
                for pattern in local.get("patterns", [])
                if pattern["horizon_bars"] == horizon and pattern["label_kind"] == key["label_kind"]
            ),
            Decimal(".5"),
        )
        source_hash = stable_id(
            "transfer_sources_v1", sorted(row["core"]["sample_id"] for row in selected)
        )
        symbols = sorted({row["core"]["symbol"] for row in selected})
        if cycle_id:
            with self.store.transaction():
                self.store.save_transfer_shadow(
                    {
                        "shadow_id": stable_id(
                            "shadow",
                            run,
                            cycle_id,
                            key["position_context"],
                            key["label_kind"],
                            horizon,
                        ),
                        "cycle_id": cycle_id,
                        "validation_group": validation_group,
                        "source_group": group,
                        **validation_key,
                        "started_at": iso(cutoff),
                        "source_cutoff_at": iso(cutoff),
                        "p": str(p),
                        "baseline": str(baseline),
                        "source_query_hash": source_hash,
                        "sources_json": canonical_json(
                            {
                                "symbols": symbols,
                                "sample_ids": [row["core"]["sample_id"] for row in selected],
                            }
                        ),
                        "status": "PENDING",
                    }
                )
        gate = brier_gate(
            self.store.transfer_shadows(validation_group),
            cutoff,
            self.config.learning.transfer.min_target_validation_samples,
        )
        status = (
            "ACTIVE"
            if gate["eligible"]
            else "SUSPENDED"
            if was_active
            or gate["sample_count"] >= self.config.learning.transfer.min_target_validation_samples
            else "VALIDATING"
        )
        details.update(
            {
                "state": status,
                "reason": gate["reason"],
                "validation": gate,
                "source_symbols": symbols[:3],
                "source_symbol_count": len(symbols),
                "source_query_hash": source_hash,
            }
        )
        with self.store.transaction():
            self.store.set_transfer_state(group, status, details, cutoff)
        if status != "ACTIVE":
            return details, None
        stats = statistics([decimal(row["core"]["return_pct"]) for row in selected])
        pattern = {
            **key,
            **stats,
            "pattern_id": group,
            "pattern_version": "transfer_v1",
            "source_scope": "TRANSFERRED",
            "normalizer_version": "relative_features_v1",
            "target_symbol": state["symbol"],
            "source_sample_count": len(selected),
            "destination_validation_sample_count": gate["sample_count"],
            "source_symbols": symbols[:3],
            "source_symbol_count": len(symbols),
            "source_query_hash": source_hash,
            "source_cutoff_at": iso(cutoff),
            "validation": gate,
            "aggregation_level": "foreign_exact_with_regime_validation",
            "interpretation": (
                "Foreign positive label frequency; destination validation is prospective "
                "by regime, not a calibrated profit forecast."
            ),
        }
        return details, pattern
