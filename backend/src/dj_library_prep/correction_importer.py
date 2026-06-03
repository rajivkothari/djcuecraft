from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from dj_library_prep import database


GENRE_FIELDS = (
    "normalized_primary_genre",
    "normalized_subgenre",
    "dj_use_tags",
)


@dataclass(frozen=True, slots=True)
class CorrectionImportSummary:
    rows_read: int
    updated_tracks: int
    unchanged_tracks: int
    skipped_missing_tracks: int


def import_corrections(
    csv_path: str | Path,
    database_path: str | Path = "djcuecraft.sqlite3",
) -> CorrectionImportSummary:
    source = Path(csv_path)
    rows_read = 0
    updated_tracks = 0
    unchanged_tracks = 0
    skipped_missing_tracks = 0

    with database.connect(database_path) as connection:
        with source.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            _validate_columns(reader.fieldnames)

            for row in reader:
                rows_read += 1
                track = _find_track(connection, row)
                if track is None:
                    skipped_missing_tracks += 1
                    continue

                corrected = _corrected_values(row)
                if not _has_changed(track, corrected):
                    unchanged_tracks += 1
                    continue

                database.apply_genre_correction(
                    connection=connection,
                    track=track,
                    corrected_primary_genre=corrected["normalized_primary_genre"],
                    corrected_subgenre=corrected["normalized_subgenre"],
                    corrected_dj_use_tags=corrected["dj_use_tags"],
                    source_file=str(source),
                )
                updated_tracks += 1

        connection.commit()

    return CorrectionImportSummary(
        rows_read=rows_read,
        updated_tracks=updated_tracks,
        unchanged_tracks=unchanged_tracks,
        skipped_missing_tracks=skipped_missing_tracks,
    )


def _validate_columns(fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise ValueError("Correction CSV is missing a header row.")

    required = {"id", "file_path", *GENRE_FIELDS}
    missing = sorted(required.difference(fieldnames))
    if missing:
        raise ValueError(f"Correction CSV is missing required columns: {', '.join(missing)}")


def _find_track(connection: Any, row: dict[str, str]) -> Any:
    track_id = row.get("id", "").strip()
    if track_id.isdigit():
        track = database.get_track_by_id(connection, int(track_id))
        if track is not None:
            return track

    file_path = row.get("file_path", "").strip()
    if file_path:
        return database.get_track_by_file_path(connection, file_path)

    return None


def _corrected_values(row: dict[str, str]) -> dict[str, str | None]:
    return {
        "normalized_primary_genre": _blank_to_none(row.get("normalized_primary_genre")),
        "normalized_subgenre": _blank_to_none(row.get("normalized_subgenre")),
        "dj_use_tags": _tags_to_json(row.get("dj_use_tags")),
    }


def _has_changed(track: Any, corrected: dict[str, str | None]) -> bool:
    for field_name in GENRE_FIELDS:
        if _database_value(track[field_name]) != _database_value(corrected[field_name]):
            return True
    return False


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _database_value(value: Any) -> str:
    return "" if value is None else str(value)


def _tags_to_json(value: str | None) -> str:
    if value is None or not value.strip():
        return "[]"

    stripped = value.strip()
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        decoded = [tag.strip() for tag in stripped.split(";") if tag.strip()]

    if isinstance(decoded, list):
        return json.dumps([str(tag) for tag in decoded])
    return json.dumps([str(decoded)])
