import json

import pytest

from dj_library_prep import database
from dj_library_prep.models import ReviewStatus, Track
from dj_library_prep.review_service import (
    list_review_history,
    list_review_tracks,
    update_review_track,
)


def test_list_review_tracks_returns_original_and_proposed_metadata(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        artist="Artist",
        title="Song",
        year="2001",
        original_genre="Salsa",
        normalized_decade="00s",
        normalized_primary_genre="Latin",
        normalized_subgenre="Salsa",
        dj_use_tags=["latin"],
        metadata_confidence=1.0,
        genre_confidence=0.84,
        review_status=ReviewStatus.NEEDS_REVIEW,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    tracks = list_review_tracks(db_path)

    assert len(tracks) == 1
    assert tracks[0]["artist"] == "Artist"
    assert tracks[0]["original_genre"] == "Salsa"
    assert tracks[0]["normalized_primary_genre"] == "Latin"
    assert tracks[0]["normalized_subgenre"] == "Salsa"
    assert tracks[0]["dj_use_tags"] == "latin"
    assert tracks[0]["review_status"] == "needs_review"
    assert tracks[0]["suggested_normalized_label"] == "00s / Latin / Salsa"
    assert tracks[0]["review_required"] is True
    assert "Year tag indicates 2001" in tracks[0]["reason"]


def test_update_review_track_edits_sqlite_only(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    audio_path = tmp_path / "song.mp3"
    audio_path.write_bytes(b"not real audio")
    track = Track(
        file_path=str(audio_path),
        file_name=audio_path.name,
        file_extension=".mp3",
        normalized_decade="90s",
        normalized_primary_genre="Hip-Hop",
        review_status=ReviewStatus.NEEDS_REVIEW,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved_track = database.list_tracks(connection)[0]

    updated = update_review_track(
        saved_track["id"],
        {
            "normalized_decade": "00s",
            "normalized_primary_genre": "Latin",
            "normalized_subgenre": "Reggaeton",
            "dj_use_tags": "latin;club",
            "review_status": "approved",
        },
        db_path,
    )

    assert updated["normalized_decade"] == "00s"
    assert updated["normalized_primary_genre"] == "Latin"
    assert updated["normalized_subgenre"] == "Reggaeton"
    assert updated["dj_use_tags"] == "latin;club"
    assert updated["review_status"] == "approved"
    assert audio_path.read_bytes() == b"not real audio"

    with database.connect(db_path) as connection:
        row = database.list_tracks(connection)[0]
    assert json.loads(row["dj_use_tags"]) == ["latin", "club"]

    history = list_review_history(saved_track["id"], db_path)
    assert len(history) == 1
    assert history[0]["file_path"] == str(audio_path)
    assert history[0]["previous_normalized_decade"] == "90s"
    assert history[0]["new_normalized_decade"] == "00s"
    assert history[0]["previous_normalized_primary_genre"] == "Hip-Hop"
    assert history[0]["new_normalized_primary_genre"] == "Latin"
    assert history[0]["previous_normalized_subgenre"] is None
    assert history[0]["new_normalized_subgenre"] == "Reggaeton"
    assert history[0]["previous_dj_use_tags"] == "[]"
    assert history[0]["new_dj_use_tags"] == '["latin", "club"]'
    assert history[0]["previous_genre_confidence"] == 0.0
    assert history[0]["new_genre_confidence"] == 0.0
    assert history[0]["previous_review_status"] == "needs_review"
    assert history[0]["new_review_status"] == "approved"
    assert history[0]["timestamp"]
    assert history[0]["action"] == "edit"
    assert history[0]["source"] == "user_edit"
    assert history[0]["confidence_at_action"] == 0.0
    assert history[0]["reason"] == "User edited the normalized metadata."


def test_track_payload_uses_stored_suggestion_columns(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="90s",
        normalized_primary_genre="Hip-Hop",
        normalized_subgenre="Boom Bap",
        genre_confidence=0.88,
        suggested_decade="90s",
        suggested_primary_genre="Hip-Hop",
        suggested_subgenre="Boom Bap",
        suggested_dj_use_tags=["hip-hop"],
        suggestion_confidence=0.88,
        review_status="needs_review",
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    tracks = list_review_tracks(db_path)

    assert tracks[0]["suggested_normalized_label"] == "90s / Hip-Hop / Boom Bap"


def test_suggestion_modified_false_when_normalized_matches_suggestion(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="90s",
        normalized_primary_genre="Hip-Hop",
        normalized_subgenre="Boom Bap",
        suggested_decade="90s",
        suggested_primary_genre="Hip-Hop",
        suggested_subgenre="Boom Bap",
        review_status="pending",
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    tracks = list_review_tracks(db_path)

    assert tracks[0]["suggestion_modified"] is False


def test_suggestion_modified_true_when_normalized_differs_from_suggestion(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="00s",
        normalized_primary_genre="Electronic",
        suggested_decade="90s",
        suggested_primary_genre="Hip-Hop",
        suggested_subgenre="Boom Bap",
        review_status="edited",
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    tracks = list_review_tracks(db_path)

    assert tracks[0]["suggestion_modified"] is True


def test_suggestion_modified_false_when_no_suggestion_stored(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="90s",
        normalized_primary_genre="Hip-Hop",
        review_status="pending",
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    tracks = list_review_tracks(db_path)

    assert tracks[0]["suggestion_modified"] is False


def test_update_review_track_rejects_unknown_fields(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved_track = database.list_tracks(connection)[0]

    with pytest.raises(ValueError):
        update_review_track(saved_track["id"], {"artist": "Changed"}, db_path)


def test_update_review_track_noop_does_not_create_history(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="Unknown",
        normalized_primary_genre="Latin",
        normalized_subgenre="Salsa",
        dj_use_tags=["latin"],
        review_status=ReviewStatus.PENDING,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved_track = database.list_tracks(connection)[0]

    update_review_track(
        saved_track["id"],
        {
            "normalized_decade": "Unknown",
            "normalized_primary_genre": "Latin",
            "normalized_subgenre": "Salsa",
            "dj_use_tags": "latin",
            "review_status": "pending",
        },
        db_path,
    )

    assert list_review_history(saved_track["id"], db_path) == []


def test_update_review_track_status_only_change_is_audited(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        review_status=ReviewStatus.NEEDS_REVIEW,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved_track = database.list_tracks(connection)[0]

    update_review_track(
        saved_track["id"],
        {"review_status": "rejected"},
        db_path,
    )

    history = list_review_history(saved_track["id"], db_path)
    assert len(history) == 1
    assert history[0]["action"] == "reject"
    assert history[0]["source"] == "user_edit"
    assert history[0]["reason"] == "User rejected the metadata suggestion."
    assert history[0]["previous_review_status"] == "needs_review"
    assert history[0]["new_review_status"] == "rejected"


def test_update_review_track_supports_edited_and_skipped_statuses(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        normalized_decade="Unknown",
        normalized_primary_genre="Hip-Hop",
        review_status=ReviewStatus.NEEDS_REVIEW,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved_track = database.list_tracks(connection)[0]

    edited = update_review_track(
        saved_track["id"],
        {
            "normalized_decade": "00s",
            "normalized_primary_genre": "Latin",
            "normalized_subgenre": "Reggaeton",
            "review_status": "edited",
        },
        db_path,
    )
    skipped = update_review_track(
        saved_track["id"],
        {"review_status": "skipped"},
        db_path,
    )

    assert edited["review_status"] == "edited"
    assert edited["normalized_decade"] == "00s"
    assert edited["normalized_primary_genre"] == "Latin"
    assert edited["normalized_subgenre"] == "Reggaeton"
    assert skipped["review_status"] == "skipped"

    history = list_review_history(saved_track["id"], db_path)
    assert len(history) == 2
    assert history[0]["action"] == "skip"
    assert history[0]["new_review_status"] == "skipped"
    assert history[1]["action"] == "edit"
    assert history[1]["new_review_status"] == "edited"
