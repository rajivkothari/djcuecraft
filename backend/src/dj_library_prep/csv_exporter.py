from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from dj_library_prep import database
from dj_library_prep.models import utc_now_iso


EXPORT_COLUMNS = [
    "id",
    "file_path",
    "file_name",
    "file_extension",
    "artist",
    "title",
    "album",
    "year",
    "original_genre",
    "normalized_decade",
    "normalized_primary_genre",
    "normalized_subgenre",
    "dj_use_tags",
    "metadata_confidence",
    "genre_confidence",
    "bpm",
    "bpm_confidence",
    "review_status",
    "missing_field_warnings",
    "created_at",
    "updated_at",
]

APPROVED_REVIEW_STATUSES = {"approved", "edited"}
APPROVED_EXPORT_COLUMNS = [
    "export_id",
    "exported_at",
    "track_id",
    "file_path",
    "file_name",
    "file_extension",
    "artist",
    "title",
    "album",
    "year",
    "original_genre",
    "approved_decade",
    "approved_primary_genre",
    "approved_subgenre",
    "approved_normalized_label",
    "approved_dj_use_tags",
    "review_status",
    "genre_confidence",
    "metadata_confidence",
    "latest_audit_id",
    "latest_audit_action",
    "latest_audit_source",
    "latest_audit_timestamp",
    "latest_audit_reason",
]


def export_tracks_to_csv(database_path: str | Path, output_path: str | Path) -> int:
    return export_approved_tracks_to_csv(database_path, output_path)


def export_approved_tracks_to_csv(
    database_path: str | Path, output_path: str | Path
) -> int:
    output = _prepare_output_path(output_path, ".csv")
    export = _approved_export(database_path)

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=APPROVED_EXPORT_COLUMNS)
        writer.writeheader()
        for record in export["records"]:
            writer.writerow(_approved_csv_row(export, record))

    return len(export["records"])


def export_approved_tracks_to_json(
    database_path: str | Path, output_path: str | Path
) -> int:
    output = _prepare_output_path(output_path, ".json")
    export = _approved_export(database_path)

    with output.open("w", encoding="utf-8") as handle:
        json.dump(export, handle, indent=2)
        handle.write("\n")

    return len(export["records"])


def export_review_tracks_to_csv(
    database_path: str | Path, output_path: str | Path
) -> int:
    output = Path(output_path)
    if output.parent and str(output.parent) != ".":
        output.parent.mkdir(parents=True, exist_ok=True)

    with database.connect(database_path) as connection:
        rows = database.list_tracks(connection)

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_row(row))

    return len(rows)


def _approved_export(database_path: str | Path) -> dict[str, Any]:
    export_id = uuid4().hex
    exported_at = utc_now_iso()

    with database.connect(database_path) as connection:
        latest_audit = _latest_audit_by_track_id(connection)
        records = [
            _approved_record(row, latest_audit.get(row["id"]))
            for row in database.list_tracks(connection)
            if row["review_status"] in APPROVED_REVIEW_STATUSES
        ]

    return {
        "export_version": "1.0",
        "export_id": export_id,
        "exported_at": exported_at,
        "source": "DJ Cue Craft",
        "export_type": "approved_metadata_sidecar",
        "included_review_statuses": sorted(APPROVED_REVIEW_STATUSES),
        "record_count": len(records),
        "records": records,
    }


def _latest_audit_by_track_id(connection: sqlite3.Connection) -> dict[int, sqlite3.Row]:
    latest: dict[int, sqlite3.Row] = {}
    for row in database.list_review_history(connection):
        track_id = row["track_id"]
        if track_id is not None and track_id not in latest:
            latest[int(track_id)] = row
    return latest


def _approved_record(row: sqlite3.Row, audit: sqlite3.Row | None) -> dict[str, Any]:
    tags = _tags_list(row["dj_use_tags"])
    return {
        "track_id": row["id"],
        "file": {
            "path": row["file_path"],
            "name": row["file_name"],
            "extension": row["file_extension"],
        },
        "original_metadata": {
            "artist": row["artist"],
            "title": row["title"],
            "album": row["album"],
            "year": row["year"],
            "genre": row["original_genre"],
        },
        "approved_metadata": {
            "decade": row["normalized_decade"],
            "primary_genre": row["normalized_primary_genre"],
            "subgenre": row["normalized_subgenre"],
            "normalized_label": _normalized_label(row),
            "dj_use_tags": tags,
        },
        "review": {
            "status": row["review_status"],
            "genre_confidence": row["genre_confidence"],
            "metadata_confidence": row["metadata_confidence"],
            "latest_audit": _audit_payload(audit),
        },
    }


def _approved_csv_row(export: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    audit = record["review"]["latest_audit"] or {}
    return {
        "export_id": export["export_id"],
        "exported_at": export["exported_at"],
        "track_id": record["track_id"],
        "file_path": record["file"]["path"],
        "file_name": record["file"]["name"],
        "file_extension": record["file"]["extension"],
        "artist": record["original_metadata"]["artist"],
        "title": record["original_metadata"]["title"],
        "album": record["original_metadata"]["album"],
        "year": record["original_metadata"]["year"],
        "original_genre": record["original_metadata"]["genre"],
        "approved_decade": record["approved_metadata"]["decade"],
        "approved_primary_genre": record["approved_metadata"]["primary_genre"],
        "approved_subgenre": record["approved_metadata"]["subgenre"],
        "approved_normalized_label": record["approved_metadata"]["normalized_label"],
        "approved_dj_use_tags": ";".join(record["approved_metadata"]["dj_use_tags"]),
        "review_status": record["review"]["status"],
        "genre_confidence": record["review"]["genre_confidence"],
        "metadata_confidence": record["review"]["metadata_confidence"],
        "latest_audit_id": audit.get("id", ""),
        "latest_audit_action": audit.get("action", ""),
        "latest_audit_source": audit.get("source", ""),
        "latest_audit_timestamp": audit.get("timestamp", ""),
        "latest_audit_reason": audit.get("reason", ""),
    }


def _audit_payload(audit: sqlite3.Row | None) -> dict[str, Any] | None:
    if audit is None:
        return None
    return {
        "id": audit["id"],
        "action": audit["action"],
        "source": audit["source"],
        "timestamp": audit["timestamp"],
        "reason": audit["reason"],
    }


def _csv_row(row: sqlite3.Row) -> dict[str, Any]:
    values = dict(row)
    values["dj_use_tags"] = _format_tags(values.get("dj_use_tags"))
    values["missing_field_warnings"] = _missing_field_warnings(values)
    return {column: values.get(column, "") for column in EXPORT_COLUMNS}


def _prepare_output_path(output_path: str | Path, expected_suffix: str) -> Path:
    output = Path(output_path)
    if output.suffix.lower() != expected_suffix:
        raise ValueError(f"Export path must end with {expected_suffix}.")
    if output.parent and str(output.parent) != ".":
        output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _normalized_label(row: sqlite3.Row) -> str:
    return " / ".join(
        [
            str(row["normalized_decade"] or "Unknown"),
            str(row["normalized_primary_genre"] or "Unknown"),
            str(row["normalized_subgenre"] or "Unknown"),
        ]
    )


def _tags_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(tag) for tag in value if str(tag).strip()]
    if not isinstance(value, str):
        return [str(value)]
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        decoded = [tag.strip() for tag in value.split(";") if tag.strip()]
    if isinstance(decoded, list):
        return [str(tag) for tag in decoded if str(tag).strip()]
    return [str(decoded)]


def _format_tags(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        return ";".join(str(tag) for tag in value)
    if not isinstance(value, str):
        return str(value)
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(decoded, list):
        return ";".join(str(tag) for tag in decoded)
    return str(decoded)


def _missing_field_warnings(values: dict[str, Any]) -> str:
    missing = []
    for field_name in ("artist", "title", "year", "original_genre"):
        if not values.get(field_name):
            missing.append(f"missing_{field_name}")
    return ";".join(missing)
