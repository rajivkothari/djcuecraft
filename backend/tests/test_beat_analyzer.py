from dj_library_prep import beat_analyzer, database
from dj_library_prep.beat_analyzer import (
    BeatAnalysisResult,
    analyze_beats_for_folder,
    propose_cue_points,
)
from dj_library_prep.models import ReviewStatus, Track


def test_propose_cue_points_uses_requested_beat_offsets() -> None:
    beat_timestamps = [float(index) for index in range(80)]

    cues = propose_cue_points(beat_timestamps, beat_confidence=0.82)

    assert [cue["cue_label"] for cue in cues] == [
        "Intro",
        "8 Beats In",
        "16 Beats In",
        "32 Beats In",
        "64 Beats In",
    ]
    assert [cue["timestamp_seconds"] for cue in cues] == [0.0, 8.0, 16.0, 32.0, 64.0]
    assert {cue["review_status"] for cue in cues} == {"pending"}


def test_propose_cue_points_marks_low_confidence_cues_needs_review() -> None:
    beat_timestamps = [float(index) for index in range(20)]

    cues = propose_cue_points(beat_timestamps, beat_confidence=0.3)

    assert [cue["cue_label"] for cue in cues] == ["Intro", "8 Beats In", "16 Beats In"]
    assert {cue["review_status"] for cue in cues} == {"needs_review"}


def test_analyze_beats_stores_beats_and_cues_in_sqlite_only(tmp_path, monkeypatch) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    audio_path = music_dir / "track.mp3"
    audio_path.write_bytes(b"not real audio")
    db_path = tmp_path / "tracks.sqlite3"

    track = Track(
        file_path=str(audio_path),
        file_name=audio_path.name,
        file_extension=".mp3",
        review_status=ReviewStatus.PENDING,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    monkeypatch.setattr(
        beat_analyzer,
        "detect_beat_timestamps",
        lambda path: BeatAnalysisResult(
            beat_timestamps=[float(index) for index in range(70)],
            beat_confidence=0.76,
        ),
    )

    summary = analyze_beats_for_folder(music_dir, db_path)

    assert summary.total_files == 1
    assert summary.analyzed_tracks == 1
    assert summary.stored_beats == 70
    assert summary.proposed_cue_points == 5
    assert summary.cue_points_needing_review == 0
    assert summary.failed_tracks == 0

    with database.connect(db_path) as connection:
        beats = database.list_beat_timestamps(connection)
        cues = database.list_cue_points(connection)

    assert len(beats) == 70
    assert beats[8]["timestamp_seconds"] == 8.0
    assert [cue["cue_label"] for cue in cues] == [
        "Intro",
        "8 Beats In",
        "16 Beats In",
        "32 Beats In",
        "64 Beats In",
    ]
    assert cues[0]["cue_confidence"] == 0.76
    assert audio_path.read_bytes() == b"not real audio"


def test_database_initializes_beat_and_cue_tables(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"

    with database.connect(db_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "beat_timestamps" in tables
    assert "cue_points" in tables
