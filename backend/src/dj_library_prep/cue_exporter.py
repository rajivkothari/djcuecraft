from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from dj_library_prep import database


CUE_EXPORT_COLUMNS = [
    "id",
    "track_id",
    "file_path",
    "file_name",
    "artist",
    "title",
    "cue_label",
    "beat_index",
    "timestamp_seconds",
    "cue_confidence",
    "review_status",
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
        rows = database.list_cue_points(connection)

    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CUE_EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_csv_row(row))

    return len(rows)


def _csv_row(row: Any) -> dict[str, object]:
    values = dict(row)
    return {column: values.get(column, "") for column in CUE_EXPORT_COLUMNS}
