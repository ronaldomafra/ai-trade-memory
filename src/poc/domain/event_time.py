"""Evidence-bound occurrence times; publication/resolution dates are never automatic proxies."""

import re
from datetime import datetime, timedelta

from poc.domain.primitives import iso, utc

UNKNOWN_CHOICES = {
    "TIMING_UNKNOWN": "Occurrence time is ambiguous or cannot be established from the item.",
    "NO_EXPLICIT_OCCURRENCE_TIME": (
        "The item has no verifiable occurrence schedule. Publication, resolution or "
        "measurement deadlines do not establish a scheduled occurrence."
    ),
}
STAMP = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})"


def occurrence_candidates(item: dict) -> dict[str, dict]:
    # Only the supplied source excerpt/title, not API metadata or collection times.
    text = str(item.get("title", "")) + "\n" + str(item.get("excerpt", ""))
    values = []
    for match in re.finditer(STAMP, text):
        try:
            stamp = iso(utc(match.group()))
        except ValueError:
            continue
        values.append(
            {
                "start": stamp,
                "end": stamp,
                "precision": "EXPLICIT_TIMESTAMP",
                "evidence_quote": text[max(0, match.start() - 60) : match.end() + 60],
            }
        )
    unique = {(value["start"], value["end"]): value for value in values}
    return {f"SOURCE_TIME_{index}": value for index, value in enumerate(list(unique.values())[:4])}


def timing_choices(item: dict) -> dict:
    return {
        **UNKNOWN_CHOICES,
        **{
            key: (
                f"{value['start']} is explicitly the occurrence schedule in this item's text; "
                "select only if it describes the happening, never a publication, correction, "
                "resolution, eligibility or measurement deadline. "
                f"Source excerpt: {value['evidence_quote']}"
            )
            for key, value in occurrence_candidates(item).items()
        },
    }


def temporal_relation(item: dict, cutoff: datetime) -> str:
    occurrence = item.get("event_time")
    if not occurrence:
        return "TIMING_UNKNOWN"
    try:
        start, end = utc(occurrence["start"]), utc(occurrence["end"])
        window_end = utc(cutoff) + timedelta(seconds=item.get("profile_window_seconds", 16 * 900))
        if start > end:
            return "TIMING_UNKNOWN"
        if utc(cutoff) <= start <= end <= window_end:
            return "IN_WINDOW"
        if end < utc(cutoff) or start > window_end:
            return "BACKGROUND"
        # A broad interval partially overlapping four hours does not guarantee timing within it.
        return "TIMING_UNKNOWN"
    except (ValueError, KeyError, TypeError):
        return "TIMING_UNKNOWN"
