import csv

from dj_library_prep import database
from dj_library_prep.csv_exporter import export_tracks_to_csv
from dj_library_prep.models import ReviewStatus, Track


def test_export_tracks_to_csv_includes_scanned_and_proposed_fields(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    csv_path = tmp_path / "tracks.csv"
    track = Track(
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
        review_status=ReviewStatus.PENDING,
    )

    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    exported_count = export_tracks_to_csv(db_path, csv_path)

    assert exported_count == 1
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["file_path"] == "C:/Music/song.mp3"
    assert rows[0]["original_genre"] == "Salsa"
    assert rows[0]["normalized_decade"] == "90s"
    assert rows[0]["normalized_primary_genre"] == "Latin"
    assert rows[0]["normalized_subgenre"] == "Salsa"
    assert rows[0]["dj_use_tags"] == "latin"
    assert rows[0]["review_status"] == "pending"
    assert rows[0]["missing_field_warnings"] == ""


def test_export_tracks_to_csv_includes_missing_field_warnings(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    csv_path = tmp_path / "exports" / "scan_results.csv"
    track = Track(
        file_path="C:/Music/incomplete.mp3",
        file_name="incomplete.mp3",
        file_extension=".mp3",
        title="Incomplete",
        normalized_decade="Unknown",
        metadata_confidence=0.25,
        genre_confidence=0.0,
        review_status=ReviewStatus.NEEDS_REVIEW,
    )

    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    exported_count = export_tracks_to_csv(db_path, csv_path)

    assert exported_count == 1
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["review_status"] == "needs_review"
    assert rows[0]["missing_field_warnings"] == (
        "missing_artist;missing_year;missing_original_genre"
    )
