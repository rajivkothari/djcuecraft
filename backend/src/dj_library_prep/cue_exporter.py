from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from dj_library_prep import database


# Cue export now reflects the per-track cue pads (the single cue model).
# Only pads that have a captured position are exported. Output is a sidecar
# review CSV; no audio files or DJ software databases are written.
CUE_EXPORT_COLUMNS = [
    "track_id",
    "file_path",
    "file_name",
    "artist",
    "title",
    "pad_index",
    "label",
    "timestamp_seconds",
    "beat_index",
    "source",
    "created_at",
    "updated_at",
]


def export_cue_points_to_csv(
    database_path: str | Path,
    output_path: str | Path,
) -> int:
    output = Path(output_path)
    if output.parent and str(output.parent) != ".":
        output.parent.mkdir(parents=True, exist_ok=True)

    with database.connect(database_path) as connection:
        rows = [
            row
            for row in database.list_all_pads(connection)
            if row["timestamp_seconds"] is not None
        ]

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CUE_EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_row(row))

    return len(rows)


def _csv_row(row: Any) -> dict[str, object]:
    values = dict(row)
    return {column: values.get(column, "") for column in CUE_EXPORT_COLUMNS}
