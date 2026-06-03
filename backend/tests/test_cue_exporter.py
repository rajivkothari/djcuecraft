import csv

from dj_library_prep import database
from dj_library_prep.cue_exporter import export_cue_points_to_csv
from dj_library_prep.models import Track


def test_export_cue_points_to_csv(tmp_path) -> None:
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
        database.replace_cue_points(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            cue_points=[
                {
                    "cue_label": "Intro",
                    "beat_index": 0,
                    "timestamp_seconds": 1.25,
                    "cue_confidence": 0.81,
                    "review_status": "pending",
                }
            ],
        )
        connection.commit()

    exported_count = export_cue_points_to_csv(db_path, csv_path)

    assert exported_count == 1
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["file_path"] == "C:/Music/song.mp3"
    assert rows[0]["file_name"] == "song.mp3"
    assert rows[0]["artist"] == "Artist"
    assert rows[0]["title"] == "Song"
    assert rows[0]["cue_label"] == "Intro"
    assert rows[0]["beat_index"] == "0"
    assert rows[0]["timestamp_seconds"] == "1.25"
    assert rows[0]["cue_confidence"] == "0.81"
    assert rows[0]["review_status"] == "pending"
