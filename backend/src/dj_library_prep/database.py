from __future__ import annotations

import sqlite3
from pathlib import Path
from collections.abc import Callable, Iterable

from dj_library_prep.models import Track, utc_now_iso


CURRENT_SCHEMA_VERSION = 4

UNREVIEWED_STATUSES = ("pending", "needs_review")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    file_extension TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    album TEXT,
    year TEXT,
    original_genre TEXT,
    normalized_decade TEXT NOT NULL,
    normalized_primary_genre TEXT,
    normalized_subgenre TEXT,
    dj_use_tags TEXT NOT NULL,
    metadata_confidence REAL NOT NULL,
    genre_confidence REAL NOT NULL,
    bpm REAL,
    bpm_confidence REAL NOT NULL DEFAULT 0.0,
    review_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CORRECTION_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS correction_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    file_path TEXT NOT NULL,
    original_suggested_genre TEXT,
    corrected_genre TEXT,
    original_normalized_primary_genre TEXT,
    original_normalized_subgenre TEXT,
    original_dj_use_tags TEXT,
    corrected_normalized_primary_genre TEXT,
    corrected_normalized_subgenre TEXT,
    corrected_dj_use_tags TEXT,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(track_id) REFERENCES tracks(id)
);
"""

REVIEW_HISTORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    file_path TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_normalized_decade TEXT,
    new_normalized_decade TEXT,
    previous_normalized_primary_genre TEXT,
    new_normalized_primary_genre TEXT,
    previous_normalized_subgenre TEXT,
    new_normalized_subgenre TEXT,
    previous_dj_use_tags TEXT,
    new_dj_use_tags TEXT,
    previous_genre_confidence REAL,
    new_genre_confidence REAL,
    confidence_at_action REAL,
    previous_review_status TEXT,
    new_review_status TEXT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    reason TEXT,
    FOREIGN KEY(track_id) REFERENCES tracks(id)
);
"""

BEAT_TIMESTAMPS_SCHEMA = """
CREATE TABLE IF NOT EXISTS beat_timestamps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    file_path TEXT NOT NULL,
    beat_index INTEGER NOT NULL,
    timestamp_seconds REAL NOT NULL,
    beat_confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(track_id) REFERENCES tracks(id)
);
"""

CUE_POINTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS cue_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER,
    file_path TEXT NOT NULL,
    cue_label TEXT NOT NULL,
    beat_index INTEGER NOT NULL,
    timestamp_seconds REAL NOT NULL,
    cue_confidence REAL NOT NULL,
    review_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(track_id) REFERENCES tracks(id),
    UNIQUE(track_id, cue_label)
);
"""

PADS_SCHEMA = """
CREATE TABLE IF NOT EXISTS pads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id INTEGER NOT NULL,
    pad_index INTEGER NOT NULL,
    label TEXT NOT NULL,
    timestamp_seconds REAL,
    beat_index INTEGER,
    source TEXT NOT NULL DEFAULT 'auto',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(track_id) REFERENCES tracks(id),
    UNIQUE(track_id, pad_index)
);
"""


def connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    if path.parent and str(path.parent) != ".":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    initialize(connection)
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    connection.execute(SCHEMA)
    connection.execute(CORRECTION_HISTORY_SCHEMA)
    connection.execute(REVIEW_HISTORY_SCHEMA)
    connection.execute(BEAT_TIMESTAMPS_SCHEMA)
    connection.execute(CUE_POINTS_SCHEMA)
    connection.execute(PADS_SCHEMA)
    _run_migrations(connection)
    connection.commit()


def get_schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def save_tracks(connection: sqlite3.Connection, tracks: Iterable[Track]) -> int:
    count = 0
    for track in tracks:
        save_track(connection, track)
        count += 1
    connection.commit()
    return count


def save_track(connection: sqlite3.Connection, track: Track) -> None:
    existing_track = get_track_by_file_path(connection, track.file_path)
    row = track.to_db_row()
    connection.execute(
        """
        INSERT INTO tracks (
            file_path, file_name, file_extension, artist, title, album, year,
            original_genre, normalized_decade, normalized_primary_genre,
            normalized_subgenre, dj_use_tags, metadata_confidence,
            genre_confidence, bpm, bpm_confidence, review_status, created_at, updated_at
        )
        VALUES (
            :file_path, :file_name, :file_extension, :artist, :title, :album, :year,
            :original_genre, :normalized_decade, :normalized_primary_genre,
            :normalized_subgenre, :dj_use_tags, :metadata_confidence,
            :genre_confidence, :bpm, :bpm_confidence, :review_status, :created_at, :updated_at
        )
        ON CONFLICT(file_path) DO UPDATE SET
            file_name = excluded.file_name,
            file_extension = excluded.file_extension,
            artist = COALESCE(excluded.artist, tracks.artist),
            title = COALESCE(excluded.title, tracks.title),
            album = COALESCE(excluded.album, tracks.album),
            year = COALESCE(excluded.year, tracks.year),
            original_genre = COALESCE(excluded.original_genre, tracks.original_genre),
            metadata_confidence = MAX(excluded.metadata_confidence, tracks.metadata_confidence),
            normalized_decade = CASE
                WHEN tracks.review_status IN ('approved', 'edited', 'rejected', 'skipped') THEN tracks.normalized_decade
                ELSE excluded.normalized_decade
            END,
            normalized_primary_genre = CASE
                WHEN tracks.review_status IN ('approved', 'edited', 'rejected', 'skipped') THEN tracks.normalized_primary_genre
                ELSE excluded.normalized_primary_genre
            END,
            normalized_subgenre = CASE
                WHEN tracks.review_status IN ('approved', 'edited', 'rejected', 'skipped') THEN tracks.normalized_subgenre
                ELSE excluded.normalized_subgenre
            END,
            dj_use_tags = CASE
                WHEN tracks.review_status IN ('approved', 'edited', 'rejected', 'skipped') THEN tracks.dj_use_tags
                ELSE excluded.dj_use_tags
            END,
            genre_confidence = CASE
                WHEN tracks.review_status IN ('approved', 'edited', 'rejected', 'skipped') THEN tracks.genre_confidence
                ELSE excluded.genre_confidence
            END,
            review_status = CASE
                WHEN tracks.review_status IN ('approved', 'edited', 'rejected', 'skipped') THEN tracks.review_status
                ELSE excluded.review_status
            END,
            updated_at = excluded.updated_at
        """,
        row,
    )
    updated_track = get_track_by_file_path(connection, track.file_path)
    if (
        existing_track is not None
        and updated_track is not None
        and existing_track["review_status"] in UNREVIEWED_STATUSES
        and _review_fields_changed(existing_track, updated_track)
    ):
        record_review_history(
            connection,
            existing_track,
            updated_track,
            source="automated_suggestion",
            action="suggestion_regenerated",
            reason="Unreviewed metadata suggestion refreshed during scan.",
        )


def list_tracks(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT
            id,
            file_path,
            file_name,
            file_extension,
            artist,
            title,
            album,
            year,
            original_genre,
            normalized_decade,
            normalized_primary_genre,
            normalized_subgenre,
            dj_use_tags,
            metadata_confidence,
            genre_confidence,
            bpm,
            bpm_confidence,
            review_status,
            created_at,
            updated_at
        FROM tracks
        ORDER BY file_path
        """
    )
    return list(cursor.fetchall())


def update_track_review_fields(
    connection: sqlite3.Connection,
    track_id: int,
    normalized_decade: str,
    normalized_primary_genre: str | None,
    normalized_subgenre: str | None,
    dj_use_tags: str,
    review_status: str,
) -> sqlite3.Row | None:
    connection.execute(
        """
        UPDATE tracks
        SET
            normalized_decade = ?,
            normalized_primary_genre = ?,
            normalized_subgenre = ?,
            dj_use_tags = ?,
            review_status = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            normalized_decade,
            normalized_primary_genre,
            normalized_subgenre,
            dj_use_tags,
            review_status,
            utc_now_iso(),
            track_id,
        ),
    )
    return get_track_by_id(connection, track_id)


def record_review_history(
    connection: sqlite3.Connection,
    previous_track: sqlite3.Row,
    new_track: sqlite3.Row,
    source: str,
    action: str | None = None,
    reason: str | None = None,
    confidence_at_action: float | None = None,
) -> bool:
    if not _review_fields_changed(previous_track, new_track):
        return False

    resolved_action = action or _infer_review_action(previous_track, new_track, source)
    resolved_confidence = (
        float(confidence_at_action)
        if confidence_at_action is not None
        else _float_or_none(new_track["genre_confidence"])
    )
    connection.execute(
        """
        INSERT INTO review_history (
            track_id,
            file_path,
            action,
            previous_normalized_decade,
            new_normalized_decade,
            previous_normalized_primary_genre,
            new_normalized_primary_genre,
            previous_normalized_subgenre,
            new_normalized_subgenre,
            previous_dj_use_tags,
            new_dj_use_tags,
            previous_genre_confidence,
            new_genre_confidence,
            confidence_at_action,
            previous_review_status,
            new_review_status,
            timestamp,
            source,
            reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_track["id"],
            new_track["file_path"],
            resolved_action,
            previous_track["normalized_decade"],
            new_track["normalized_decade"],
            previous_track["normalized_primary_genre"],
            new_track["normalized_primary_genre"],
            previous_track["normalized_subgenre"],
            new_track["normalized_subgenre"],
            previous_track["dj_use_tags"],
            new_track["dj_use_tags"],
            previous_track["genre_confidence"],
            new_track["genre_confidence"],
            resolved_confidence,
            previous_track["review_status"],
            new_track["review_status"],
            utc_now_iso(),
            source,
            reason,
        ),
    )
    return True


def list_review_history_by_track_id(
    connection: sqlite3.Connection, track_id: int
) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT *
        FROM review_history
        WHERE track_id = ?
        ORDER BY timestamp DESC, id DESC
        """,
        (track_id,),
    )
    return list(cursor.fetchall())


def list_review_history(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT *
        FROM review_history
        ORDER BY timestamp DESC, id DESC
        """
    )
    return list(cursor.fetchall())


def update_track_bpm(
    connection: sqlite3.Connection,
    file_path: str,
    bpm: float | None,
    bpm_confidence: float,
    review_status: str,
) -> None:
    connection.execute(
        """
        UPDATE tracks
        SET
            bpm = ?,
            bpm_confidence = ?,
            review_status = ?,
            updated_at = ?
        WHERE file_path = ?
        """,
        (bpm, bpm_confidence, review_status, utc_now_iso(), file_path),
    )


def replace_beat_timestamps(
    connection: sqlite3.Connection,
    track_id: int | None,
    file_path: str,
    beat_timestamps: list[float],
    beat_confidence: float,
) -> int:
    connection.execute("DELETE FROM beat_timestamps WHERE file_path = ?", (file_path,))
    timestamp = utc_now_iso()
    connection.executemany(
        """
        INSERT INTO beat_timestamps (
            track_id, file_path, beat_index, timestamp_seconds, beat_confidence, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (track_id, file_path, index, beat_time, beat_confidence, timestamp)
            for index, beat_time in enumerate(beat_timestamps)
        ],
    )
    return len(beat_timestamps)


def replace_cue_points(
    connection: sqlite3.Connection,
    track_id: int | None,
    file_path: str,
    cue_points: list[dict[str, object]],
) -> int:
    connection.execute("DELETE FROM cue_points WHERE file_path = ?", (file_path,))
    timestamp = utc_now_iso()
    connection.executemany(
        """
        INSERT INTO cue_points (
            track_id,
            file_path,
            cue_label,
            beat_index,
            timestamp_seconds,
            cue_confidence,
            review_status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                track_id,
                file_path,
                cue_point["cue_label"],
                cue_point["beat_index"],
                cue_point["timestamp_seconds"],
                cue_point["cue_confidence"],
                cue_point["review_status"],
                timestamp,
                timestamp,
            )
            for cue_point in cue_points
        ],
    )
    return len(cue_points)


def insert_missing_cue_points(
    connection: sqlite3.Connection,
    track_id: int | None,
    file_path: str,
    cue_points: list[dict[str, object]],
) -> list[dict[str, object]]:
    existing_labels = _existing_cue_labels(connection, track_id, file_path)
    missing_cue_points = [
        cue_point
        for cue_point in cue_points
        if str(cue_point["cue_label"]) not in existing_labels
    ]
    if not missing_cue_points:
        return []

    timestamp = utc_now_iso()
    connection.executemany(
        """
        INSERT INTO cue_points (
            track_id,
            file_path,
            cue_label,
            beat_index,
            timestamp_seconds,
            cue_confidence,
            review_status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                track_id,
                file_path,
                cue_point["cue_label"],
                cue_point["beat_index"],
                cue_point["timestamp_seconds"],
                cue_point["cue_confidence"],
                cue_point["review_status"],
                timestamp,
                timestamp,
            )
            for cue_point in missing_cue_points
        ],
    )
    return missing_cue_points


def get_cue_point_by_id(
    connection: sqlite3.Connection, cue_id: int
) -> sqlite3.Row | None:
    cursor = connection.execute("SELECT * FROM cue_points WHERE id = ?", (cue_id,))
    return cursor.fetchone()


def update_cue_label(
    connection: sqlite3.Connection,
    cue_id: int,
    new_label: str,
) -> sqlite3.Row | None:
    connection.execute(
        "UPDATE cue_points SET cue_label = ?, updated_at = ? WHERE id = ?",
        (new_label, utc_now_iso(), cue_id),
    )
    connection.commit()
    return get_cue_point_by_id(connection, cue_id)


def list_cue_points(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT
            cue_points.id,
            cue_points.track_id,
            cue_points.file_path,
            tracks.file_name,
            tracks.artist,
            tracks.title,
            cue_points.cue_label,
            cue_points.beat_index,
            cue_points.timestamp_seconds,
            cue_points.cue_confidence,
            cue_points.review_status,
            cue_points.created_at,
            cue_points.updated_at
        FROM cue_points
        LEFT JOIN tracks ON tracks.id = cue_points.track_id
        ORDER BY cue_points.file_path, cue_points.beat_index
        """
    )
    return list(cursor.fetchall())


def list_pads(connection: sqlite3.Connection, track_id: int) -> list[sqlite3.Row]:
    cursor = connection.execute(
        "SELECT * FROM pads WHERE track_id = ? ORDER BY pad_index",
        (track_id,),
    )
    return list(cursor.fetchall())


def get_pad(
    connection: sqlite3.Connection, track_id: int, pad_index: int
) -> sqlite3.Row | None:
    cursor = connection.execute(
        "SELECT * FROM pads WHERE track_id = ? AND pad_index = ?",
        (track_id, pad_index),
    )
    return cursor.fetchone()


def upsert_pad(
    connection: sqlite3.Connection,
    track_id: int,
    pad_index: int,
    label: str,
    timestamp_seconds: float | None,
    beat_index: int | None,
    source: str,
) -> sqlite3.Row | None:
    timestamp = utc_now_iso()
    connection.execute(
        """
        INSERT INTO pads (
            track_id, pad_index, label, timestamp_seconds, beat_index,
            source, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(track_id, pad_index) DO UPDATE SET
            label = excluded.label,
            timestamp_seconds = excluded.timestamp_seconds,
            beat_index = excluded.beat_index,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (
            track_id,
            pad_index,
            label,
            timestamp_seconds,
            beat_index,
            source,
            timestamp,
            timestamp,
        ),
    )
    connection.commit()
    return get_pad(connection, track_id, pad_index)


def clear_pad(connection: sqlite3.Connection, track_id: int, pad_index: int) -> None:
    connection.execute(
        "DELETE FROM pads WHERE track_id = ? AND pad_index = ?",
        (track_id, pad_index),
    )
    connection.commit()


def clear_all_pads(connection: sqlite3.Connection, track_id: int) -> None:
    connection.execute("DELETE FROM pads WHERE track_id = ?", (track_id,))
    connection.commit()


def list_all_pads(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT
            pads.id,
            pads.track_id,
            tracks.file_path,
            tracks.file_name,
            tracks.artist,
            tracks.title,
            pads.pad_index,
            pads.label,
            pads.timestamp_seconds,
            pads.beat_index,
            pads.source,
            pads.created_at,
            pads.updated_at
        FROM pads
        LEFT JOIN tracks ON tracks.id = pads.track_id
        ORDER BY tracks.file_path, pads.pad_index
        """
    )
    return list(cursor.fetchall())


def list_beat_timestamps_for_track(
    connection: sqlite3.Connection, track_id: int
) -> list[float]:
    cursor = connection.execute(
        """
        SELECT timestamp_seconds
        FROM beat_timestamps
        WHERE track_id = ?
        ORDER BY beat_index
        """,
        (track_id,),
    )
    return [float(row["timestamp_seconds"]) for row in cursor.fetchall()]


def _existing_cue_labels(
    connection: sqlite3.Connection,
    track_id: int | None,
    file_path: str,
) -> set[str]:
    if track_id is not None:
        cursor = connection.execute(
            "SELECT cue_label FROM cue_points WHERE track_id = ?",
            (track_id,),
        )
    else:
        cursor = connection.execute(
            "SELECT cue_label FROM cue_points WHERE file_path = ?",
            (file_path,),
        )
    return {str(row["cue_label"]) for row in cursor.fetchall()}


def list_beat_timestamps(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT *
        FROM beat_timestamps
        ORDER BY file_path, beat_index
        """
    )
    return list(cursor.fetchall())


def get_track_by_id(connection: sqlite3.Connection, track_id: int) -> sqlite3.Row | None:
    cursor = connection.execute("SELECT * FROM tracks WHERE id = ?", (track_id,))
    return cursor.fetchone()


def get_track_by_file_path(
    connection: sqlite3.Connection, file_path: str
) -> sqlite3.Row | None:
    cursor = connection.execute("SELECT * FROM tracks WHERE file_path = ?", (file_path,))
    return cursor.fetchone()


def apply_genre_correction(
    connection: sqlite3.Connection,
    track: sqlite3.Row,
    corrected_decade: str,
    corrected_primary_genre: str | None,
    corrected_subgenre: str | None,
    corrected_dj_use_tags: str,
    source_file: str,
) -> None:
    original_primary = track["normalized_primary_genre"]
    original_subgenre = track["normalized_subgenre"]
    original_tags = track["dj_use_tags"]
    timestamp = utc_now_iso()

    connection.execute(
        """
        UPDATE tracks
        SET
            normalized_primary_genre = ?,
            normalized_subgenre = ?,
            normalized_decade = ?,
            dj_use_tags = ?,
            review_status = 'approved',
            updated_at = ?
        WHERE id = ?
        """,
        (
            corrected_primary_genre,
            corrected_subgenre,
            corrected_decade,
            corrected_dj_use_tags,
            timestamp,
            track["id"],
        ),
    )
    connection.execute(
        """
        INSERT INTO correction_history (
            track_id,
            file_path,
            original_suggested_genre,
            corrected_genre,
            original_normalized_primary_genre,
            original_normalized_subgenre,
            original_dj_use_tags,
            corrected_normalized_primary_genre,
            corrected_normalized_subgenre,
            corrected_dj_use_tags,
            source_file,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            track["id"],
            track["file_path"],
            _genre_label(original_primary, original_subgenre, original_tags),
            _genre_label(
                corrected_primary_genre, corrected_subgenre, corrected_dj_use_tags
            ),
            original_primary,
            original_subgenre,
            original_tags,
            corrected_primary_genre,
            corrected_subgenre,
            corrected_dj_use_tags,
            source_file,
            timestamp,
        ),
    )
    updated = get_track_by_id(connection, track["id"])
    if updated is not None:
        record_review_history(
            connection,
            track,
            updated,
            source="user_edit",
            action="edit",
            reason=f"Correction imported from {source_file}.",
        )


def list_correction_history(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    cursor = connection.execute(
        """
        SELECT *
        FROM correction_history
        ORDER BY created_at, id
        """
    )
    return list(cursor.fetchall())


def _genre_label(primary: str | None, subgenre: str | None, tags: str | None) -> str:
    parts = [part for part in (primary, subgenre) if part]
    if tags:
        parts.append(f"tags={tags}")
    return " / ".join(parts)


def _run_migrations(connection: sqlite3.Connection) -> None:
    schema_version = get_schema_version(connection)
    for target_version, migration in MIGRATIONS:
        if schema_version < target_version:
            migration(connection)
            _set_schema_version(connection, target_version)
            schema_version = target_version


def _migrate_legacy_bpm_columns(connection: sqlite3.Connection) -> None:
    _ensure_column(connection, "tracks", "bpm", "REAL")
    _ensure_column(connection, "tracks", "bpm_confidence", "REAL NOT NULL DEFAULT 0.0")


def _migrate_review_history_audit_columns(connection: sqlite3.Connection) -> None:
    _ensure_column(
        connection,
        "review_history",
        "action",
        "TEXT NOT NULL DEFAULT 'edit'",
    )
    _ensure_column(connection, "review_history", "confidence_at_action", "REAL")
    _ensure_column(connection, "review_history", "reason", "TEXT")


def _migrate_track_lookup_indexes(connection: sqlite3.Connection) -> None:
    indexes = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    statements = [
        ("idx_beat_timestamps_track_id", "CREATE INDEX IF NOT EXISTS idx_beat_timestamps_track_id ON beat_timestamps(track_id)"),
        ("idx_cue_points_track_id", "CREATE INDEX IF NOT EXISTS idx_cue_points_track_id ON cue_points(track_id)"),
        ("idx_review_history_track_id", "CREATE INDEX IF NOT EXISTS idx_review_history_track_id ON review_history(track_id)"),
        ("idx_correction_history_track_id", "CREATE INDEX IF NOT EXISTS idx_correction_history_track_id ON correction_history(track_id)"),
    ]
    for index_name, sql in statements:
        if index_name not in indexes:
            connection.execute(sql)


def _migrate_pads_table(connection: sqlite3.Connection) -> None:
    connection.execute(PADS_SCHEMA)
    indexes = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
    if "idx_pads_track_id" not in indexes:
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_pads_track_id ON pads(track_id)"
        )


MIGRATIONS: tuple[tuple[int, Callable[[sqlite3.Connection], None]], ...] = (
    (1, _migrate_legacy_bpm_columns),
    (2, _migrate_review_history_audit_columns),
    (3, _migrate_track_lookup_indexes),
    (CURRENT_SCHEMA_VERSION, _migrate_pads_table),
)


def _set_schema_version(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(f"PRAGMA user_version = {version}")


def _ensure_column(
    connection: sqlite3.Connection, table_name: str, column_name: str, definition: str
) -> None:
    columns = {
        row["name"] for row in connection.execute(f"PRAGMA table_info({table_name})")
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def _review_fields_changed(previous_track: sqlite3.Row, new_track: sqlite3.Row) -> bool:
    tracked_fields = (
        "normalized_decade",
        "normalized_primary_genre",
        "normalized_subgenre",
        "dj_use_tags",
        "genre_confidence",
        "review_status",
    )
    return any(
        _comparable_value(previous_track[field]) != _comparable_value(new_track[field])
        for field in tracked_fields
    )


def _comparable_value(value: object) -> str:
    return "" if value is None else str(value)


def _infer_review_action(
    previous_track: sqlite3.Row, new_track: sqlite3.Row, source: str
) -> str:
    if source == "bulk_action" and new_track["review_status"] == "approved":
        return "bulk_approve"

    if _normalized_values_changed(previous_track, new_track):
        return "edit"

    status_action = {
        "approved": "approve",
        "edited": "edit",
        "rejected": "reject",
        "skipped": "skip",
    }.get(str(new_track["review_status"]))
    if status_action:
        return status_action

    return "review_status_changed"


def _normalized_values_changed(
    previous_track: sqlite3.Row, new_track: sqlite3.Row
) -> bool:
    tracked_fields = (
        "normalized_decade",
        "normalized_primary_genre",
        "normalized_subgenre",
        "dj_use_tags",
    )
    return any(
        _comparable_value(previous_track[field]) != _comparable_value(new_track[field])
        for field in tracked_fields
    )


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    return float(value)
