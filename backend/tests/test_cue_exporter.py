import csv

from dj_library_prep import database, pads
from dj_library_prep.cue_exporter import export_cue_points_to_csv
from dj_library_prep.models import Track


def test_export_cue_points_to_csv_exports_pads(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    csv_path = tmp_path / "exports" / "cue_points.csv"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        artist="Artist",
        title="Song",
    )

    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        saved_track = database.list_tracks(connection)[0]

    track_id = saved_track["id"]
    pads.set_pad(track_id, 0, label="Intro", timestamp_seconds=1.25, database_path=db_path)
    pads.set_pad(track_id, 1, label="Drop", timestamp_seconds=16.0, database_path=db_path)

    exported_count = export_cue_points_to_csv(db_path, csv_path)

    assert exported_count == 2
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["file_path"] == "C:/Music/song.mp3"
    assert rows[0]["file_name"] == "song.mp3"
    assert rows[0]["artist"] == "Artist"
    assert rows[0]["pad_index"] == "0"
    assert rows[0]["label"] == "Intro"
    assert rows[0]["timestamp_seconds"] == "1.25"
    assert rows[0]["source"] == "manual"
    assert rows[1]["label"] == "Drop"


def test_export_cue_points_skips_empty_pad_slots(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    csv_path = tmp_path / "cue_points.csv"
    track = Track(
        file_path="C:/Music/song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        track_id = database.list_tracks(connection)[0]["id"]

    # one positioned pad; the other 7 slots are empty and must not export
    pads.set_pad(track_id, 0, label="Intro", timestamp_seconds=0.0, database_path=db_path)

    exported_count = export_cue_points_to_csv(db_path, csv_path)

    assert exported_count == 1
