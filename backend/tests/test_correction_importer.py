import csv
import json

from dj_library_prep import database
from dj_library_prep.correction_importer import import_corrections
from dj_library_prep.csv_exporter import EXPORT_COLUMNS
from dj_library_prep.models import ReviewStatus, Track


def test_import_corrections_updates_changed_genre_fields_and_history(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    csv_path = tmp_path / "exports" / "scan_results_corrected.csv"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        artist="Artist",
        title="Song",
        original_genre="Hip Hop",
        normalized_primary_genre="Hip-Hop",
        dj_use_tags=[],
        genre_confidence=0.92,
        review_status=ReviewStatus.NEEDS_REVIEW,
    )

    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved_track = database.list_tracks(connection)[0]

    _write_corrected_csv(
        csv_path,
        {
            "id": saved_track["id"],
            "file_path": saved_track["file_path"],
            "file_name": saved_track["file_name"],
            "file_extension": saved_track["file_extension"],
            "artist": saved_track["artist"],
            "title": saved_track["title"],
            "album": "",
            "year": "",
            "original_genre": saved_track["original_genre"],
            "normalized_decade": saved_track["normalized_decade"],
            "normalized_primary_genre": "R&B",
            "normalized_subgenre": "Soul",
            "dj_use_tags": "crate;warmup",
            "metadata_confidence": saved_track["metadata_confidence"],
            "genre_confidence": saved_track["genre_confidence"],
            "review_status": saved_track["review_status"],
            "missing_field_warnings": "",
            "created_at": saved_track["created_at"],
            "updated_at": saved_track["updated_at"],
        },
    )

    summary = import_corrections(csv_path, db_path)

    assert summary.rows_read == 1
    assert summary.updated_tracks == 1
    assert summary.unchanged_tracks == 0
    assert summary.skipped_missing_tracks == 0

    with database.connect(db_path) as connection:
        updated_track = database.list_tracks(connection)[0]
        history = database.list_correction_history(connection)
        review_history = database.list_review_history(connection)

    assert updated_track["normalized_primary_genre"] == "R&B"
    assert updated_track["normalized_subgenre"] == "Soul"
    assert json.loads(updated_track["dj_use_tags"]) == ["crate", "warmup"]
    assert updated_track["review_status"] == "approved"

    assert len(history) == 1
    assert history[0]["file_path"] == "C:/Music/song.mp3"
    assert history[0]["original_suggested_genre"] == "Hip-Hop / tags=[]"
    assert history[0]["corrected_genre"] == 'R&B / Soul / tags=["crate", "warmup"]'
    assert history[0]["source_file"] == str(csv_path)

    assert len(review_history) == 1
    assert review_history[0]["action"] == "edit"
    assert review_history[0]["source"] == "user_edit"
    assert review_history[0]["confidence_at_action"] == 0.92
    assert review_history[0]["reason"] == f"Correction imported from {csv_path}."
    assert review_history[0]["previous_normalized_primary_genre"] == "Hip-Hop"
    assert review_history[0]["new_normalized_primary_genre"] == "R&B"
    assert review_history[0]["previous_normalized_subgenre"] is None
    assert review_history[0]["new_normalized_subgenre"] == "Soul"
    assert review_history[0]["previous_dj_use_tags"] == "[]"
    assert review_history[0]["new_dj_use_tags"] == '["crate", "warmup"]'
    assert review_history[0]["previous_review_status"] == "needs_review"
    assert review_history[0]["new_review_status"] == "approved"


def test_import_corrections_leaves_unchanged_tracks_unapproved(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    csv_path = tmp_path / "scan_results_corrected.csv"
    track = Track(
        file_path="C:/Music/salsa.mp3",
        file_name="salsa.mp3",
        file_extension=".mp3",
        original_genre="Salsa",
        normalized_primary_genre="Latin",
        normalized_subgenre="Salsa",
        dj_use_tags=["latin"],
        review_status=ReviewStatus.NEEDS_REVIEW,
    )

    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved_track = database.list_tracks(connection)[0]

    _write_corrected_csv(
        csv_path,
        {
            "id": saved_track["id"],
            "file_path": saved_track["file_path"],
            "file_name": saved_track["file_name"],
            "file_extension": saved_track["file_extension"],
            "artist": "",
            "title": "",
            "album": "",
            "year": "",
            "original_genre": "Salsa",
            "normalized_decade": "Unknown",
            "normalized_primary_genre": "Latin",
            "normalized_subgenre": "Salsa",
            "dj_use_tags": "latin",
            "metadata_confidence": "0.0",
            "genre_confidence": "0.84",
            "review_status": "needs_review",
            "missing_field_warnings": "",
            "created_at": saved_track["created_at"],
            "updated_at": saved_track["updated_at"],
        },
    )

    summary = import_corrections(csv_path, db_path)

    assert summary.updated_tracks == 0
    assert summary.unchanged_tracks == 1
    with database.connect(db_path) as connection:
        unchanged_track = database.list_tracks(connection)[0]
        history = database.list_correction_history(connection)
        review_history = database.list_review_history(connection)

    assert unchanged_track["review_status"] == "needs_review"
    assert history == []
    assert review_history == []


def test_import_corrections_does_not_overwrite_suggestion_columns(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    csv_path = tmp_path / "exports" / "corrected.csv"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        original_genre="Hip Hop",
        normalized_decade="90s",
        normalized_primary_genre="Hip-Hop",
        suggested_decade="90s",
        suggested_primary_genre="Hip-Hop",
        suggestion_confidence=0.9,
        genre_confidence=0.9,
        review_status=ReviewStatus.NEEDS_REVIEW,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved_track = database.list_tracks(connection)[0]

    _write_corrected_csv(
        csv_path,
        {
            "id": saved_track["id"],
            "file_path": saved_track["file_path"],
            "file_name": saved_track["file_name"],
            "file_extension": saved_track["file_extension"],
            "artist": "",
            "title": "",
            "album": "",
            "year": "",
            "original_genre": saved_track["original_genre"],
            "normalized_decade": "90s",
            "normalized_primary_genre": "R&B",
            "normalized_subgenre": "Soul",
            "dj_use_tags": "rb",
            "metadata_confidence": "0.0",
            "genre_confidence": "0.9",
            "review_status": "needs_review",
            "missing_field_warnings": "",
            "created_at": saved_track["created_at"],
            "updated_at": saved_track["updated_at"],
        },
    )

    import_corrections(csv_path, db_path)

    with database.connect(db_path) as connection:
        row = database.list_tracks(connection)[0]

    assert row["normalized_primary_genre"] == "R&B"
    assert row["suggested_primary_genre"] == "Hip-Hop"
    assert row["suggestion_confidence"] == 0.9


def _write_corrected_csv(path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerow(row)
