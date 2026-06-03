import sqlite3

from dj_library_prep import database


def test_initialize_sets_current_schema_version(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"

    with database.connect(db_path) as connection:
        schema_version = database.get_schema_version(connection)

    assert schema_version == database.CURRENT_SCHEMA_VERSION


def test_initialize_migrates_legacy_tracks_table_to_current_schema(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    _create_legacy_tracks_table(db_path)

    with database.connect(db_path) as connection:
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(tracks)")
        }
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        schema_version = database.get_schema_version(connection)

    assert "bpm" in columns
    assert "bpm_confidence" in columns
    assert "review_history" in tables
    assert "beat_timestamps" in tables
    assert "cue_points" in tables
    assert schema_version == database.CURRENT_SCHEMA_VERSION


def _create_legacy_tracks_table(db_path) -> None:
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE tracks (
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
            review_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()
