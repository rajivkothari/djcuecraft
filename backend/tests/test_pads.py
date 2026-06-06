import pytest

from dj_library_prep import database, pads
from dj_library_prep.models import Track


def _track_with_beats(db_path, beat_count=300):
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved = database.get_track_by_file_path(connection, track.file_path)
        database.replace_beat_timestamps(
            connection,
            track_id=saved["id"],
            file_path=saved["file_path"],
            beat_timestamps=[round(i * 0.5, 3) for i in range(beat_count)],
            beat_confidence=0.8,
        )
        connection.commit()
    return saved["id"]


def test_list_pads_returns_eight_empty_slots_for_new_track(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track_id = _track_with_beats(db_path)

    pad_slots = pads.list_pads_for_track(track_id, db_path)

    assert len(pad_slots) == 8
    assert [pad["pad_index"] for pad in pad_slots] == list(range(8))
    assert all(pad["timestamp_seconds"] is None for pad in pad_slots)
    assert pad_slots[0]["label"] == "Intro"
    assert pad_slots[1]["label"] == "Phrase 1"


def test_autofill_places_phrase_pads_from_beats(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track_id = _track_with_beats(db_path, beat_count=300)

    pad_slots = pads.autofill_pads(track_id, phrase_length=32, database_path=db_path)

    # beats are 0.5s apart, so beat N is at N*0.5 seconds
    assert pad_slots[0]["timestamp_seconds"] == 0.0  # beat 0
    assert pad_slots[1]["timestamp_seconds"] == 16.0  # beat 32
    assert pad_slots[2]["timestamp_seconds"] == 32.0  # beat 64
    assert all(pad["source"] == "auto" for pad in pad_slots)


def test_autofill_skips_pads_beyond_beat_count(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    # only 100 beats: pads at beats 0,32,64,96 fit; 128,160,192,224 do not
    track_id = _track_with_beats(db_path, beat_count=100)

    pad_slots = pads.autofill_pads(track_id, phrase_length=32, database_path=db_path)

    assert pad_slots[3]["timestamp_seconds"] == 48.0  # beat 96
    assert pad_slots[4]["timestamp_seconds"] is None  # beat 128 out of range


def test_autofill_requires_stored_beats(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track = Track(
        file_path="C:/Music/no-beats.mp3",
        file_name="no-beats.mp3",
        file_extension=".mp3",
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        track_id = database.get_track_by_file_path(connection, track.file_path)["id"]

    with pytest.raises(ValueError, match="No beats stored"):
        pads.autofill_pads(track_id, database_path=db_path)


def test_set_pad_renames_without_losing_position(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track_id = _track_with_beats(db_path)
    pads.autofill_pads(track_id, database_path=db_path)

    renamed = pads.set_pad(track_id, 1, label="Drop", database_path=db_path)

    assert renamed["label"] == "Drop"
    assert renamed["timestamp_seconds"] == 16.0  # position preserved
    assert renamed["source"] == "manual"


def test_set_pad_recapture_updates_position_and_clears_beat(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track_id = _track_with_beats(db_path)
    pads.autofill_pads(track_id, database_path=db_path)

    recaptured = pads.set_pad(
        track_id, 2, timestamp_seconds=41.234, database_path=db_path
    )

    assert recaptured["timestamp_seconds"] == 41.234
    assert recaptured["beat_index"] is None
    assert recaptured["source"] == "manual"


def test_autofill_preserves_manual_pads(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track_id = _track_with_beats(db_path)
    pads.autofill_pads(track_id, database_path=db_path)
    pads.set_pad(track_id, 1, label="My Drop", timestamp_seconds=99.0, database_path=db_path)

    refreshed = pads.autofill_pads(track_id, database_path=db_path)

    assert refreshed[1]["label"] == "My Drop"
    assert refreshed[1]["timestamp_seconds"] == 99.0
    assert refreshed[1]["source"] == "manual"
    # auto pads around it are still auto
    assert refreshed[0]["source"] == "auto"
    assert refreshed[2]["source"] == "auto"


def test_set_pad_rejects_empty_label(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track_id = _track_with_beats(db_path)

    with pytest.raises(ValueError, match="empty"):
        pads.set_pad(track_id, 0, label="   ", database_path=db_path)


def test_set_pad_rejects_out_of_range_index(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track_id = _track_with_beats(db_path)

    with pytest.raises(ValueError, match="between 0 and 7"):
        pads.set_pad(track_id, 8, label="X", database_path=db_path)


def test_clear_pad_removes_slot(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    track_id = _track_with_beats(db_path)
    pads.autofill_pads(track_id, database_path=db_path)

    pads.clear_pad(track_id, 0, db_path)

    refreshed = pads.list_pads_for_track(track_id, db_path)
    assert refreshed[0]["timestamp_seconds"] is None
    assert refreshed[0]["source"] is None
