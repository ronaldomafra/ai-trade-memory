"""Validated, atomic initial imports and immutable accumulated JSONL exports."""

import json
import os
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from poc.application.learning import learning_protocol
from poc.config import parse_config
from poc.domain.dataset import encoded_records, records_hash, validate_record
from poc.domain.primitives import DomainError, canonical_json, iso, stable_id, utc

HEADER_FIELDS = {
    "record_type",
    "schema_version",
    "dataset_id",
    "revision",
    "created_at",
    "export_cutoff_at",
    "origin_run_id",
    "sample_count",
    "samples_sha256",
    "predecessors",
    "composition",
    "exclusions",
}


def read_dataset(path: Path, cutoff: datetime) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(64 * 1024 * 1024 + 1)
    if len(raw) > 64 * 1024 * 1024:
        raise DomainError("Dataset exceeds the 64 MB V1 import bound")
    first, sep, body = raw.partition(b"\n")
    if not sep or (body and not body.endswith(b"\n")):
        raise DomainError("Dataset must contain complete UTF-8 JSONL lines")
    try:
        header = json.loads(first)
        if (
            not isinstance(header, dict)
            or set(header) != HEADER_FIELDS
            or header["record_type"] != "dataset_metadata"
            or type(header["schema_version"]) is not int
            or header["schema_version"] not in (1, 2)
        ):
            raise DomainError("Unsupported dataset metadata schema")
        if (
            header["samples_sha256"] != records_hash(body)
            or utc(header["export_cutoff_at"]) > utc(cutoff)
            or utc(header["created_at"]) > utc(cutoff)
        ):
            raise DomainError("Dataset integrity or cutoff is invalid")
        identity = {k: v for k, v in header.items() if k != "dataset_id"}
        if header["dataset_id"] != stable_id("dataset_v" + str(header["schema_version"]), identity):
            raise DomainError("Dataset identity mismatch")
        if (
            type(header["revision"]) is not int
            or header["revision"] < 1
            or not isinstance(header["predecessors"], list)
        ):
            raise DomainError("Invalid dataset revision/ancestry")
        for prior in header["predecessors"]:
            if set(prior) != {"dataset_id", "file_hash"} or any(
                not isinstance(v, str) or len(v) != 64 for v in prior.values()
            ):
                raise DomainError("Invalid dataset predecessor")
        records = []
        unique = set()
        for line in body.splitlines():
            record = json.loads(line)
            validate_record(record, utc(header["export_cutoff_at"]))
            for origin in record["origins"]:
                source_config = parse_config(origin["protocol_parameters"])
                if learning_protocol(source_config) != record["core"]["protocol_hash"]:
                    raise DomainError("Origin protocol does not match example")
                if record["core"]["label_version"] == "profile_labels_v2":
                    core = record["core"]
                    definition = source_config.profile_definition
                    features = core["features"]
                    if (
                        features.get("decision_interval") != core["interval"]
                        or features.get("trend_interval") != core["trend_interval"]
                        or features.get("rsi_period") != source_config.indicators.rsi
                        or list(features.get("return_horizons_bars", []))
                        != list(source_config.indicators.return_horizons_bars)
                        or len(features.get("returns_pct", []))
                        != len(source_config.indicators.return_horizons_bars)
                    ):
                        raise DomainError(
                            "Feature duration/indicator metadata does not match its origin"
                        )
                    if (
                        core["interval"] != source_config.market.interval
                        or core["trend_interval"] != source_config.market.trend_interval
                        or core["profile_id"] != definition.profile.profile_id
                        or core["profile_version"] != str(definition.profile.version)
                        or core["horizon_bars"]
                        not in source_config.learning.evaluation_horizons_bars
                        or core["outcome_quote_window_seconds"]
                        != source_config.learning.outcome_quote_window_seconds
                    ):
                        raise DomainError("Profile label metadata does not match its origin")
                if source_config.simulation.trading_fee_pct_per_side / 100 != Decimal(
                    record["core"]["fee_fraction"]
                ) or source_config.simulation.slippage_pct_per_side / 100 != Decimal(
                    record["core"]["slippage_fraction"]
                ):
                    raise DomainError("Origin costs do not match example")
            identity = record["core"]["sample_id"]
            if identity in unique:
                raise DomainError(
                    "Duplicate examples must be merged with all origins before export"
                )
            unique.add(identity)
            records.append(record)
            if len(records) > 100000:
                raise DomainError("Dataset exceeds 100000 observations")
        if type(header["sample_count"]) is not int or header["sample_count"] != len(records):
            raise DomainError("Dataset count mismatch")
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeDecodeError) as exc:
        if isinstance(exc, DomainError):
            raise
        raise DomainError("Malformed learning dataset") from exc
    return {"header": header, "records": records, "file_hash": records_hash(raw)}


class DatasetFiles:
    def __init__(self, database):
        self.db = database

    def imported(self) -> dict | None:
        row = self.db.connection.execute("SELECT * FROM dataset_imports").fetchone()
        return dict(row) if row else None

    def install(self, data: dict, now: datetime) -> dict:
        header = data["header"]
        with self.db.transaction():
            previous = self.imported()
            if previous:
                if (
                    previous["dataset_id"] == header["dataset_id"]
                    and previous["file_hash"] == data["file_hash"]
                ):
                    return {**previous, "idempotent": True}
                raise DomainError("The initial dataset is already fixed for this session")
            if self.db.connection.execute("SELECT 1 FROM decisions LIMIT 1").fetchone():
                raise DomainError(
                    "Initial learning import is only allowed before the first decision"
                )
            for record in data["records"]:
                for origin in record["origins"]:
                    self.db.save_learning_record(record["core"], origin, now)
            self.db.connection.execute(
                "INSERT INTO dataset_imports VALUES(?,?,?,?,?,?)",
                (
                    header["dataset_id"],
                    data["file_hash"],
                    canonical_json(header),
                    iso(now),
                    len(data["records"]),
                    "ACTIVE",
                ),
            )
            self.db.event(
                "INITIAL_DATASET_IMPORTED",
                {
                    "dataset_id": header["dataset_id"],
                    "file_hash": data["file_hash"],
                    "sample_count": len(data["records"]),
                },
                now,
                stable_id("dataset-import", header["dataset_id"]),
            )
        return {
            "dataset_id": header["dataset_id"],
            "sample_count": len(data["records"]),
            "file_hash": data["file_hash"],
            "imported_at": iso(now),
            "idempotent": False,
        }

    def import_path(self, path: Path, now: datetime) -> dict:
        return self.install(read_dataset(path, now), now)

    def export(self, path: Path, cutoff: datetime) -> dict:
        self.db.connection.execute("BEGIN")
        try:
            records = self.db.learning_records(cutoff)
            excluded = sum(record["core"]["fixture"] for record in records)
            records = [record for record in records if not record["core"]["fixture"]]
            for record in records:
                record["origins"].sort(key=lambda origin: origin["origin_id"])
                validate_record(record, cutoff)
            body = encoded_records(records)
            predecessors = [
                {"dataset_id": row["dataset_id"], "file_hash": row["file_hash"]}
                for row in self.db.connection.execute(
                    "SELECT * FROM dataset_imports ORDER BY dataset_id"
                )
            ]
            # Preserve the full ancestry; a reexport never renames source examples.
            all_prior = {row["dataset_id"]: row for row in predecessors}
            for row in self.db.connection.execute("SELECT header_json FROM dataset_imports"):
                for prior in json.loads(row[0])["predecessors"]:
                    all_prior[prior["dataset_id"]] = prior
            composition = {}
            for record in records:
                symbol = record["core"]["symbol"]
                composition[symbol] = composition.get(symbol, 0) + 1
            header = {
                "record_type": "dataset_metadata",
                "schema_version": 2
                if any(r["core"]["label_version"] == "profile_labels_v2" for r in records)
                else 1,
                "revision": 1
                + max(
                    [
                        json.loads(row[0])["revision"]
                        for row in self.db.connection.execute(
                            "SELECT header_json FROM dataset_imports"
                        )
                    ],
                    default=0,
                ),
                "created_at": iso(cutoff),
                "export_cutoff_at": iso(cutoff),
                "origin_run_id": self.db.run()["run_id"],
                "sample_count": len(records),
                "samples_sha256": records_hash(body),
                "predecessors": sorted(all_prior.values(), key=lambda row: row["dataset_id"]),
                "composition": composition,
                "exclusions": {
                    "fixture_examples": excluded,
                    "pending_or_unavailable": self.db.connection.execute(
                        "SELECT COUNT(*) FROM decision_outcomes WHERE status!='MATURED'"
                    ).fetchone()[0],
                },
            }
            header["dataset_id"] = stable_id("dataset_v" + str(header["schema_version"]), header)
        finally:
            self.db.connection.rollback()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write((canonical_json(header) + "\n").encode() + body)
                stream.flush()
                os.fsync(stream.fileno())
            # link publishes atomically and fails if a previous version already exists.
            os.link(temporary, path)
        finally:
            os.unlink(temporary)
        return {
            "path": str(path),
            "dataset_id": header["dataset_id"],
            "sample_count": len(records),
            "file_hash": records_hash((canonical_json(header) + "\n").encode() + body),
        }
