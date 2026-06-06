import pytest

from dj_library_prep import beat_analyzer, database
from dj_library_prep.beat_analyzer import (
    BeatAnalysisResult,
    CueTemplate,
    analyze_beats_for_folder,
    parse_cue_template,
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


def test_propose_cue_points_uses_custom_cue_template() -> None:
    beat_timestamps = [float(index) for index in range(40)]
    cue_template = (
        CueTemplate("Load", 0),
        CueTemplate("Drop Prep", 32),
        CueTemplate("Too Far", 64),
    )

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.81,
        cue_template=cue_template,
    )

    assert [cue["cue_label"] for cue in cues] == ["Load", "Drop Prep"]
    assert [cue["beat_index"] for cue in cues] == [0, 32]
    assert [cue["timestamp_seconds"] for cue in cues] == [0.0, 32.0]


def test_parse_cue_template_validates_custom_cue_setup() -> None:
    cues = parse_cue_template(["Load=0", "Drop Prep=32"])

    assert cues == (
        CueTemplate("Load", 0),
        CueTemplate("Drop Prep", 32),
    )

    with pytest.raises(ValueError, match="Duplicate cue label"):
        parse_cue_template(["Load=0", "Load=32"])

    with pytest.raises(ValueError, match="cannot be negative"):
        parse_cue_template(["Before Start=-1"])

    with pytest.raises(ValueError, match="at least one cue"):
        parse_cue_template([])


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


def test_analyze_beats_stores_custom_auto_cue_setup(tmp_path, monkeypatch) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    audio_path = music_dir / "track.mp3"
    audio_path.write_bytes(b"not real audio")
    db_path = tmp_path / "tracks.sqlite3"

    monkeypatch.setattr(
        beat_analyzer,
        "detect_beat_timestamps",
        lambda path: BeatAnalysisResult(
            beat_timestamps=[float(index) for index in range(40)],
            beat_confidence=0.8,
        ),
    )

    summary = analyze_beats_for_folder(
        music_dir,
        db_path,
        cue_template=(
            CueTemplate("Load", 0),
            CueTemplate("Drop Prep", 32),
        ),
    )

    assert summary.proposed_cue_points == 2

    with database.connect(db_path) as connection:
        cues = database.list_cue_points(connection)

    assert [cue["cue_label"] for cue in cues] == ["Load", "Drop Prep"]
    assert [cue["beat_index"] for cue in cues] == [0, 32]


def test_analyze_beats_fills_missing_cues_without_overwriting_existing_cues(
    tmp_path, monkeypatch
) -> None:
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
        saved_track = database.list_tracks(connection)[0]
        database.replace_cue_points(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            cue_points=[
                {
                    "cue_label": "Load",
                    "beat_index": 4,
                    "timestamp_seconds": 1.5,
                    "cue_confidence": 0.42,
                    "review_status": "approved",
                }
            ],
        )
        connection.commit()

    monkeypatch.setattr(
        beat_analyzer,
        "detect_beat_timestamps",
        lambda path: BeatAnalysisResult(
            beat_timestamps=[float(index) for index in range(40)],
            beat_confidence=0.8,
        ),
    )

    summary = analyze_beats_for_folder(
        music_dir,
        db_path,
        cue_template=(
            CueTemplate("Load", 0),
            CueTemplate("Drop Prep", 32),
        ),
    )

    assert summary.proposed_cue_points == 1

    with database.connect(db_path) as connection:
        cues = database.list_cue_points(connection)

    assert [cue["cue_label"] for cue in cues] == ["Load", "Drop Prep"]
    assert cues[0]["beat_index"] == 4
    assert cues[0]["timestamp_seconds"] == 1.5
    assert cues[0]["cue_confidence"] == 0.42
    assert cues[0]["review_status"] == "approved"
    assert cues[1]["beat_index"] == 32
    assert cues[1]["timestamp_seconds"] == 32.0


def test_failed_beat_analysis_preserves_existing_beats_and_cues(
    tmp_path, monkeypatch
) -> None:
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
        saved_track = database.list_tracks(connection)[0]
        database.replace_beat_timestamps(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            beat_timestamps=[float(index) for index in range(50)],
            beat_confidence=0.8,
        )
        database.replace_cue_points(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            cue_points=[
                {
                    "cue_label": "Load",
                    "beat_index": 4,
                    "timestamp_seconds": 1.5,
                    "cue_confidence": 0.42,
                    "review_status": "approved",
                }
            ],
        )
        connection.commit()

    # Detection now fails (returns no beats), e.g. moved/corrupt file.
    monkeypatch.setattr(
        beat_analyzer,
        "detect_beat_timestamps",
        lambda path: BeatAnalysisResult(beat_timestamps=[], beat_confidence=0.0),
    )

    summary = analyze_beats_for_folder(music_dir, db_path)

    assert summary.total_files == 1
    assert summary.failed_tracks == 1
    assert summary.analyzed_tracks == 0
    assert summary.stored_beats == 0
    assert summary.proposed_cue_points == 0
    assert summary.cue_points_needing_review == 0

    with database.connect(db_path) as connection:
        beats = database.list_beat_timestamps(connection)
        cues = database.list_cue_points(connection)

    # Existing beats and the approved cue must survive the failed re-analysis.
    assert len(beats) == 50
    assert beats[8]["timestamp_seconds"] == 8.0
    assert [cue["cue_label"] for cue in cues] == ["Load"]
    assert cues[0]["beat_index"] == 4
    assert cues[0]["timestamp_seconds"] == 1.5
    assert cues[0]["review_status"] == "approved"
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
