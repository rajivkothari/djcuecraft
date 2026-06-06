import sqlite3

from dj_library_prep import database
from dj_library_prep.models import ReviewStatus, Track


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
        review_history_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(review_history)")
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
    assert "action" in review_history_columns
    assert "confidence_at_action" in review_history_columns
    assert "reason" in review_history_columns
    assert "beat_timestamps" in tables
    assert "cue_points" in tables
    assert schema_version == database.CURRENT_SCHEMA_VERSION


def test_initialize_migrates_legacy_review_history_to_audit_schema(tmp_path) -> None:
    db_path = tmp_path / "legacy_history.sqlite3"
    _create_version_1_review_history_table(db_path)

    with database.connect(db_path) as connection:
        review_history_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(review_history)")
        }
        schema_version = database.get_schema_version(connection)

    assert "action" in review_history_columns
    assert "confidence_at_action" in review_history_columns
    assert "reason" in review_history_columns
    assert schema_version == database.CURRENT_SCHEMA_VERSION


def test_save_track_rescan_preserves_reviewed_suggestions_and_existing_metadata(
    tmp_path,
) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    original_track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        artist="Artist",
        title="Song",
        album="Album",
        year="1997",
        original_genre="Salsa",
        normalized_decade="90s",
        normalized_primary_genre="Latin",
        normalized_subgenre="Salsa",
        dj_use_tags=["latin"],
        metadata_confidence=1.0,
        genre_confidence=0.84,
        bpm=124.0,
        bpm_confidence=0.7,
        review_status=ReviewStatus.APPROVED,
    )
    rescanned_track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        title="Updated Song",
        normalized_decade="Unknown",
        metadata_confidence=0.25,
        genre_confidence=0.0,
        review_status=ReviewStatus.NEEDS_REVIEW,
    )

    with database.connect(db_path) as connection:
        database.save_tracks(connection, [original_track])
        database.save_tracks(connection, [rescanned_track])
        saved_track = database.list_tracks(connection)[0]

    assert saved_track["artist"] == "Artist"
    assert saved_track["title"] == "Updated Song"
    assert saved_track["album"] == "Album"
    assert saved_track["year"] == "1997"
    assert saved_track["original_genre"] == "Salsa"
    assert saved_track["metadata_confidence"] == 1.0
    assert saved_track["normalized_decade"] == "90s"
    assert saved_track["normalized_primary_genre"] == "Latin"
    assert saved_track["normalized_subgenre"] == "Salsa"
    assert saved_track["dj_use_tags"] == '["latin"]'
    assert saved_track["genre_confidence"] == 0.84
    assert saved_track["bpm"] == 124.0
    assert saved_track["bpm_confidence"] == 0.7
    assert saved_track["review_status"] == "approved"


def test_save_track_rescan_preserves_rejected_review_decision(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    original_track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="90s",
        normalized_primary_genre="Latin",
        normalized_subgenre="Salsa",
        dj_use_tags=["latin"],
        genre_confidence=0.84,
        review_status=ReviewStatus.REJECTED,
    )
    rescanned_track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="00s",
        normalized_primary_genre="Pop",
        normalized_subgenre="Dance Pop",
        dj_use_tags=["peak-time"],
        genre_confidence=0.92,
        review_status=ReviewStatus.PENDING,
    )

    with database.connect(db_path) as connection:
        database.save_tracks(connection, [original_track])
        database.save_tracks(connection, [rescanned_track])
        saved_track = database.list_tracks(connection)[0]

    assert saved_track["normalized_decade"] == "90s"
    assert saved_track["normalized_primary_genre"] == "Latin"
    assert saved_track["normalized_subgenre"] == "Salsa"
    assert saved_track["dj_use_tags"] == '["latin"]'
    assert saved_track["genre_confidence"] == 0.84
    assert saved_track["review_status"] == "rejected"


def test_save_track_rescan_preserves_edited_and_skipped_review_decisions(
    tmp_path,
) -> None:
    db_path = tmp_path / "tracks.sqlite3"

    for status in (ReviewStatus.EDITED, ReviewStatus.SKIPPED):
        original_track = Track(
            file_path=f"C:/Music/{status.value}.mp3",
            file_name=f"{status.value}.mp3",
            file_extension=".mp3",
            normalized_decade="90s",
            normalized_primary_genre="Latin",
            normalized_subgenre="Salsa",
            dj_use_tags=["latin"],
            genre_confidence=0.84,
            review_status=status,
        )
        rescanned_track = Track(
            file_path=f"C:/Music/{status.value}.mp3",
            file_name=f"{status.value}.mp3",
            file_extension=".mp3",
            normalized_decade="00s",
            normalized_primary_genre="Pop",
            normalized_subgenre="Dance Pop",
            dj_use_tags=["peak-time"],
            genre_confidence=0.92,
            review_status=ReviewStatus.PENDING,
        )

        with database.connect(db_path) as connection:
            database.save_tracks(connection, [original_track])
            database.save_tracks(connection, [rescanned_track])
            saved_track = database.get_track_by_file_path(
                connection,
                original_track.file_path,
            )

        assert saved_track["normalized_decade"] == "90s"
        assert saved_track["normalized_primary_genre"] == "Latin"
        assert saved_track["normalized_subgenre"] == "Salsa"
        assert saved_track["dj_use_tags"] == '["latin"]'
        assert saved_track["genre_confidence"] == 0.84
        assert saved_track["review_status"] == status.value


def test_save_track_rescan_refreshes_unreviewed_suggestions(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    original_track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="Unknown",
        normalized_primary_genre=None,
        normalized_subgenre=None,
        dj_use_tags=[],
        genre_confidence=0.0,
        review_status=ReviewStatus.NEEDS_REVIEW,
    )
    rescanned_track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="90s",
        normalized_primary_genre="Latin",
        normalized_subgenre="Salsa",
        dj_use_tags=["latin"],
        genre_confidence=0.84,
        review_status=ReviewStatus.PENDING,
    )

    with database.connect(db_path) as connection:
        database.save_tracks(connection, [original_track])
        database.save_tracks(connection, [rescanned_track])
        saved_track = database.list_tracks(connection)[0]

    assert saved_track["normalized_decade"] == "90s"
    assert saved_track["normalized_primary_genre"] == "Latin"
    assert saved_track["normalized_subgenre"] == "Salsa"
    assert saved_track["dj_use_tags"] == '["latin"]'
    assert saved_track["genre_confidence"] == 0.84
    assert saved_track["review_status"] == "pending"

    with database.connect(db_path) as connection:
        history = database.list_review_history(connection)

    assert len(history) == 1
    assert history[0]["action"] == "suggestion_regenerated"
    assert history[0]["source"] == "automated_suggestion"
    assert history[0]["confidence_at_action"] == 0.84
    assert history[0]["reason"] == "Unreviewed metadata suggestion refreshed during scan."
    assert history[0]["previous_review_status"] == "needs_review"
    assert history[0]["new_review_status"] == "pending"


def test_initialize_creates_track_lookup_indexes(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    with database.connect(db_path) as connection:
        indexes = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

    assert "idx_beat_timestamps_track_id" in indexes
    assert "idx_cue_points_track_id" in indexes
    assert "idx_review_history_track_id" in indexes
    assert "idx_correction_history_track_id" in indexes


def test_initialize_creates_pads_table(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    with database.connect(db_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

    assert "pads" in tables
    assert "idx_pads_track_id" in indexes


def test_migration_adds_pads_table_to_existing_database(tmp_path) -> None:
    db_path = tmp_path / "pre_pads.sqlite3"
    _create_version_2_database(db_path)

    with database.connect(db_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        schema_version = database.get_schema_version(connection)

    assert "pads" in tables
    assert schema_version == database.CURRENT_SCHEMA_VERSION


def test_migration_adds_indexes_to_existing_database(tmp_path) -> None:
    db_path = tmp_path / "pre_index.sqlite3"
    _create_version_2_database(db_path)

    with database.connect(db_path) as connection:
        indexes = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        schema_version = database.get_schema_version(connection)

    assert "idx_beat_timestamps_track_id" in indexes
    assert "idx_cue_points_track_id" in indexes
    assert "idx_review_history_track_id" in indexes
    assert "idx_correction_history_track_id" in indexes
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


def test_migration_adds_suggestion_columns_to_existing_database(tmp_path) -> None:
    db_path = tmp_path / "pre_suggestion.sqlite3"
    _create_legacy_tracks_table(db_path)

    with database.connect(db_path) as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(tracks)")
        }
        schema_version = database.get_schema_version(connection)

    assert "suggested_decade" in columns
    assert "suggested_primary_genre" in columns
    assert "suggested_subgenre" in columns
    assert "suggested_dj_use_tags" in columns
    assert "suggestion_confidence" in columns
    assert schema_version == database.CURRENT_SCHEMA_VERSION


def test_suggestion_columns_backfilled_from_normalized_on_migration(tmp_path) -> None:
    db_path = tmp_path / "backfill.sqlite3"
    _create_legacy_tracks_table(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        INSERT INTO tracks (
            file_path, file_name, file_extension, normalized_decade,
            normalized_primary_genre, normalized_subgenre, dj_use_tags,
            metadata_confidence, genre_confidence, review_status,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "C:/Music/song.mp3", "song.mp3", ".mp3", "90s",
            "Hip-Hop", "Boom Bap", '["hip-hop"]',
            1.0, 0.9, "pending", "2024-01-01T00:00:00", "2024-01-01T00:00:00",
        ),
    )
    connection.commit()
    connection.close()

    with database.connect(db_path) as connection:
        row = connection.execute("SELECT * FROM tracks").fetchone()

    assert row["suggested_decade"] == "90s"
    assert row["suggested_primary_genre"] == "Hip-Hop"
    assert row["suggested_subgenre"] == "Boom Bap"
    assert row["suggested_dj_use_tags"] == '["hip-hop"]'
    assert row["suggestion_confidence"] == 0.9


def test_save_track_stores_suggestion_columns_on_first_insert(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="00s",
        normalized_primary_genre="Electronic",
        normalized_subgenre="House",
        dj_use_tags=["electronic", "dance"],
        genre_confidence=0.85,
        suggested_decade="00s",
        suggested_primary_genre="Electronic",
        suggested_subgenre="House",
        suggested_dj_use_tags=["electronic", "dance"],
        suggestion_confidence=0.85,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        row = database.list_tracks(connection)[0]

    assert row["suggested_decade"] == "00s"
    assert row["suggested_primary_genre"] == "Electronic"
    assert row["suggested_subgenre"] == "House"
    assert row["suggestion_confidence"] == 0.85


def test_rescan_does_not_overwrite_suggestion_columns(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track_v1 = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="90s",
        normalized_primary_genre="Hip-Hop",
        suggested_decade="90s",
        suggested_primary_genre="Hip-Hop",
        suggestion_confidence=0.9,
    )
    track_v2 = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="00s",
        normalized_primary_genre="Electronic",
        suggested_decade="00s",
        suggested_primary_genre="Electronic",
        suggestion_confidence=0.75,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track_v1])
        database.save_tracks(connection, [track_v2])
        row = database.list_tracks(connection)[0]

    assert row["suggested_decade"] == "90s"
    assert row["suggested_primary_genre"] == "Hip-Hop"
    assert row["suggestion_confidence"] == 0.9


def test_list_tracks_includes_suggestion_columns(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/track.mp3",
        file_name="track.mp3",
        file_extension=".mp3",
        suggested_decade="10s",
        suggested_primary_genre="Dance",
        suggested_subgenre="EDM",
        suggested_dj_use_tags=["dance"],
        suggestion_confidence=0.8,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        rows = database.list_tracks(connection)

    assert rows[0]["suggested_decade"] == "10s"
    assert rows[0]["suggested_primary_genre"] == "Dance"
    assert rows[0]["suggested_subgenre"] == "EDM"
    assert rows[0]["suggestion_confidence"] == 0.8


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


def _create_version_2_database(db_path) -> None:
    """Schema at version 2 — has BPM columns and audit columns but no indexes."""
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA user_version = 2")
    connection.execute(
        """
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            file_name TEXT NOT NULL,
            file_extension TEXT NOT NULL,
            normalized_decade TEXT NOT NULL,
            dj_use_tags TEXT NOT NULL,
            metadata_confidence REAL NOT NULL,
            genre_confidence REAL NOT NULL,
            bpm REAL,
            bpm_confidence REAL NOT NULL DEFAULT 0.0,
            review_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE beat_timestamps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER,
            file_path TEXT NOT NULL,
            beat_index INTEGER NOT NULL,
            timestamp_seconds REAL NOT NULL,
            beat_confidence REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE cue_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER,
            file_path TEXT NOT NULL,
            cue_label TEXT NOT NULL,
            beat_index INTEGER NOT NULL,
            timestamp_seconds REAL NOT NULL,
            cue_confidence REAL NOT NULL,
            review_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER,
            file_path TEXT NOT NULL,
            action TEXT NOT NULL DEFAULT 'edit',
            confidence_at_action REAL,
            reason TEXT,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE correction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER,
            file_path TEXT NOT NULL,
            source_file TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()


def _create_version_1_review_history_table(db_path) -> None:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA user_version = 1")
    connection.execute(
        """
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL UNIQUE,
            file_name TEXT NOT NULL,
            file_extension TEXT NOT NULL,
            normalized_decade TEXT NOT NULL,
            dj_use_tags TEXT NOT NULL,
            metadata_confidence REAL NOT NULL,
            genre_confidence REAL NOT NULL,
            bpm REAL,
            bpm_confidence REAL NOT NULL DEFAULT 0.0,
            review_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER,
            file_path TEXT NOT NULL,
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
            previous_review_status TEXT,
            new_review_status TEXT,
            timestamp TEXT NOT NULL,
            source TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()
