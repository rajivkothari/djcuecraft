from __future__ import annotations

import sqlite3
from pathlib import Path
from collections.abc import Iterable

from dj_library_prep.models import Track, utc_now_iso


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
    connection.execute(BEAT_TIMESTAMPS_SCHEMA)
    connection.execute(CUE_POINTS_SCHEMA)
    _ensure_column(connection, "tracks", "bpm", "REAL")
    _ensure_column(connection, "tracks", "bpm_confidence", "REAL NOT NULL DEFAULT 0.0")
    connection.commit()


def save_tracks(connection: sqlite3.Connection, tracks: Iterable[Track]) -> int:
    count = 0
    for track in tracks:
        save_track(connection, track)
        count += 1
    connection.commit()
    return count


def save_track(connection: sqlite3.Connection, track: Track) -> None:
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
            artist = excluded.artist,
            title = excluded.title,
            album = excluded.album,
            year = excluded.year,
            original_genre = excluded.original_genre,
            normalized_decade = excluded.normalized_decade,
            normalized_primary_genre = excluded.normalized_primary_genre,
            normalized_subgenre = excluded.normalized_subgenre,
            dj_use_tags = excluded.dj_use_tags,
            metadata_confidence = excluded.metadata_confidence,
            genre_confidence = excluded.genre_confidence,
            review_status = excluded.review_status,
            updated_at = excluded.updated_at
        """,
        row,
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
            dj_use_tags = ?,
            review_status = 'approved',
            updated_at = ?
        WHERE id = ?
        """,
        (
            corrected_primary_genre,
            corrected_subgenre,
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
