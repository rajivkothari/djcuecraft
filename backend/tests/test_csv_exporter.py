import csv
import json

import pytest

from dj_library_prep import database
from dj_library_prep.csv_exporter import (
    export_approved_tracks_to_json,
    export_tracks_to_csv,
)
from dj_library_prep.models import ReviewStatus, Track
from dj_library_prep.review_service import update_review_track


def test_export_tracks_to_csv_includes_only_approved_and_edited_records(
    tmp_path,
) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    csv_path = tmp_path / "exports" / "approved.csv"

    with database.connect(db_path) as connection:
        database.save_tracks(
            connection,
            [
                Track(
                    file_path="C:/Music/approved.mp3",
                    file_name="approved.mp3",
                    file_extension=".mp3",
                    artist="Artist",
                    title="Approved Song",
                    album="Album",
                    year="1997",
                    original_genre="Salsa",
                    normalized_decade="90s",
                    normalized_primary_genre="Latin",
                    normalized_subgenre="Salsa",
                    dj_use_tags=["latin"],
                    metadata_confidence=1.0,
                    genre_confidence=0.84,
                    review_status=ReviewStatus.APPROVED,
                ),
                Track(
                    file_path="C:/Music/edit-me.mp3",
                    file_name="edit-me.mp3",
                    file_extension=".mp3",
                    original_genre="Hip Hop",
                    normalized_decade="90s",
                    normalized_primary_genre="Hip-Hop",
                    review_status=ReviewStatus.NEEDS_REVIEW,
                ),
                Track(
                    file_path="C:/Music/pending.mp3",
                    file_name="pending.mp3",
                    file_extension=".mp3",
                    normalized_primary_genre="Pop",
                    review_status=ReviewStatus.PENDING,
                ),
            ],
        )
        edit_track = database.get_track_by_file_path(connection, "C:/Music/edit-me.mp3")

    update_review_track(
        edit_track["id"],
        {
            "normalized_decade": "00s",
            "normalized_primary_genre": "Hip-Hop",
            "normalized_subgenre": "Club Rap",
            "dj_use_tags": "club;peak-time",
            "review_status": "edited",
        },
        db_path,
    )

    exported_count = export_tracks_to_csv(db_path, csv_path)

    assert exported_count == 2
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert {row["file_name"] for row in rows} == {"approved.mp3", "edit-me.mp3"}

    approved = next(row for row in rows if row["file_name"] == "approved.mp3")
    assert approved["artist"] == "Artist"
    assert approved["original_genre"] == "Salsa"
    assert approved["approved_decade"] == "90s"
    assert approved["approved_primary_genre"] == "Latin"
    assert approved["approved_subgenre"] == "Salsa"
    assert approved["approved_normalized_label"] == "90s / Latin / Salsa"
    assert approved["approved_dj_use_tags"] == "latin"
    assert approved["review_status"] == "approved"
    assert approved["genre_confidence"] == "0.84"
    assert approved["latest_audit_id"] == ""

    edited = next(row for row in rows if row["file_name"] == "edit-me.mp3")
    assert edited["approved_decade"] == "00s"
    assert edited["approved_subgenre"] == "Club Rap"
    assert edited["approved_dj_use_tags"] == "club;peak-time"
    assert edited["review_status"] == "edited"
    assert edited["latest_audit_action"] == "edit"
    assert edited["latest_audit_source"] == "user_edit"
    assert edited["latest_audit_reason"] == "User edited the normalized metadata."
    assert edited["export_id"]
    assert edited["exported_at"]


def test_export_approved_tracks_to_json_writes_sidecar_structure(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    json_path = tmp_path / "exports" / "approved.json"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        artist="Artist",
        title="Song",
        year="2004",
        original_genre="Hip-Hop/Rap",
        normalized_decade="00s",
        normalized_primary_genre="Hip-Hop",
        normalized_subgenre="Club Rap",
        dj_use_tags=["club"],
        genre_confidence=0.92,
        review_status=ReviewStatus.EDITED,
    )

    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    exported_count = export_approved_tracks_to_json(db_path, json_path)

    assert exported_count == 1
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["export_version"] == "1.0"
    assert payload["export_type"] == "approved_metadata_sidecar"
    assert payload["included_review_statuses"] == ["approved", "edited"]
    assert payload["record_count"] == 1
    assert payload["records"][0]["file"]["path"] == "C:/Music/song.mp3"
    assert payload["records"][0]["original_metadata"]["genre"] == "Hip-Hop/Rap"
    assert payload["records"][0]["approved_metadata"]["normalized_label"] == (
        "00s / Hip-Hop / Club Rap"
    )
    assert payload["records"][0]["approved_metadata"]["dj_use_tags"] == ["club"]
    assert payload["records"][0]["review"]["status"] == "edited"
    assert payload["records"][0]["review"]["genre_confidence"] == 0.92


def test_export_refuses_audio_file_extension(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"not real audio")

    with pytest.raises(ValueError):
        export_tracks_to_csv(db_path, audio_path)

    assert audio_path.read_bytes() == b"not real audio"
