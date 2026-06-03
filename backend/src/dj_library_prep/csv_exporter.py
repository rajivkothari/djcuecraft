from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from dj_library_prep import database


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


def export_tracks_to_csv(database_path: str | Path, output_path: str | Path) -> int:
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


def _csv_row(row: sqlite3.Row) -> dict[str, Any]:
    values = dict(row)
    values["dj_use_tags"] = _format_tags(values.get("dj_use_tags"))
    values["missing_field_warnings"] = _missing_field_warnings(values)
    return {column: values.get(column, "") for column in EXPORT_COLUMNS}


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
