import sqlite3

from dj_library_prep import database
from dj_library_prep.models import Track


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


def test_insert_missing_cue_points_preserves_existing_cues(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
    )

    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved_track = database.list_tracks(connection)[0]
        database.replace_cue_points(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            cue_points=[
                {
                    "cue_label": "Intro",
                    "beat_index": 2,
                    "timestamp_seconds": 0.5,
                    "cue_confidence": 0.5,
                    "review_status": "approved",
                }
            ],
        )

        inserted_cues = database.insert_missing_cue_points(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            cue_points=[
                {
                    "cue_label": "Intro",
                    "beat_index": 0,
                    "timestamp_seconds": 0.0,
                    "cue_confidence": 0.9,
                    "review_status": "pending",
                },
                {
                    "cue_label": "Drop Prep",
                    "beat_index": 32,
                    "timestamp_seconds": 16.0,
                    "cue_confidence": 0.9,
                    "review_status": "pending",
                },
            ],
        )
        connection.commit()

        cues = database.list_cue_points(connection)

    assert [cue["cue_label"] for cue in inserted_cues] == ["Drop Prep"]
    assert [cue["cue_label"] for cue in cues] == ["Intro", "Drop Prep"]
    assert cues[0]["beat_index"] == 2
    assert cues[0]["timestamp_seconds"] == 0.5
    assert cues[0]["cue_confidence"] == 0.5
    assert cues[0]["review_status"] == "approved"
    assert cues[1]["beat_index"] == 32


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
