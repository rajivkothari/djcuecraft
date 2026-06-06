import pytest

from dj_library_prep import beat_analyzer, database
from dj_library_prep.beat_analyzer import (
    BeatAnalysisResult,
    CUE_PRESETS,
    DEFAULT_CUE_PRESET,
    CueTemplate,
    analyze_beats_for_folder,
    cue_template_for_preset,
    parse_cue_template,
    propose_cue_points,
)
from dj_library_prep.models import ReviewStatus, Track


def test_propose_cue_points_uses_requested_beat_offsets() -> None:
    beat_timestamps = [float(index) for index in range(80)]

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.82,
        cue_template=cue_template_for_preset("starter"),
    )

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

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.3,
        cue_template=cue_template_for_preset("starter"),
    )

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

    summary = analyze_beats_for_folder(
        music_dir, db_path, cue_template=cue_template_for_preset("starter")
    )

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


# --- new tests for time_fraction support and performance/minimix presets ---


def test_default_preset_is_performance() -> None:
    assert DEFAULT_CUE_PRESET == "performance"


def test_cue_template_time_fraction_defaults_to_none() -> None:
    cue = CueTemplate("Intro", 0)
    assert cue.time_fraction is None
    assert cue.beat_index == 0


def test_cue_template_time_fraction_cue() -> None:
    cue = CueTemplate("Outro", time_fraction=0.9)
    assert cue.time_fraction == 0.9
    assert cue.beat_index is None


def test_performance_preset_structure() -> None:
    preset = CUE_PRESETS["performance"]
    beat_indexed = [c for c in preset if c.time_fraction is None]
    time_fractioned = [c for c in preset if c.time_fraction is not None]
    assert len(beat_indexed) == 5
    assert len(time_fractioned) == 3
    beat_labels = [c.cue_label for c in beat_indexed]
    assert "Intro" in beat_labels
    assert "8 Beats In" in beat_labels
    assert "16 Beats In" in beat_labels
    assert "32 Beats In" in beat_labels
    assert "64 Beats In" in beat_labels
    frac_labels = [c.cue_label for c in time_fractioned]
    assert "Mid" in frac_labels
    assert "Last Chorus" in frac_labels
    assert "Outro" in frac_labels
    for cue in time_fractioned:
        assert 0.0 <= cue.time_fraction <= 1.0


def test_minimix_preset_structure() -> None:
    preset = CUE_PRESETS["minimix"]
    assert len(preset) == 8
    beat_indexed = [c for c in preset if c.time_fraction is None]
    time_fractioned = [c for c in preset if c.time_fraction is not None]
    assert len(beat_indexed) == 1
    assert len(time_fractioned) == 7
    assert beat_indexed[0].cue_label == "Track 1"
    assert beat_indexed[0].beat_index == 0


def test_propose_cue_points_resolves_time_fraction_to_nearest_beat() -> None:
    # beats at 0, 1, 2, ... 9 seconds; total duration = 10s
    beat_timestamps = [float(i) for i in range(10)]

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.8,
        cue_template=(CueTemplate("Mid", time_fraction=0.5),),
        total_duration_seconds=10.0,
    )

    assert len(cues) == 1
    assert cues[0]["cue_label"] == "Mid"
    # 0.5 * 10 = 5.0 → beat index 5, timestamp 5.0
    assert cues[0]["timestamp_seconds"] == 5.0
    assert cues[0]["beat_index"] == 5


def test_propose_cue_points_skips_time_fraction_without_duration() -> None:
    beat_timestamps = [float(i) for i in range(20)]

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.8,
        cue_template=(
            CueTemplate("Intro", 0),
            CueTemplate("Outro", time_fraction=0.9),
        ),
        # total_duration_seconds not provided → Outro skipped
    )

    assert len(cues) == 1
    assert cues[0]["cue_label"] == "Intro"


def test_propose_cue_points_time_fraction_at_boundaries() -> None:
    beat_timestamps = [float(i) for i in range(10)]

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.8,
        cue_template=(
            CueTemplate("Start", time_fraction=0.0),
            CueTemplate("End", time_fraction=1.0),
        ),
        total_duration_seconds=9.0,
    )

    assert len(cues) == 2
    # 0.0 * 9 = 0.0 → beat 0
    assert cues[0]["timestamp_seconds"] == 0.0
    # 1.0 * 9 = 9.0 → beat 9
    assert cues[1]["timestamp_seconds"] == 9.0


def test_propose_cue_points_time_fraction_snaps_to_nearest_beat() -> None:
    # beats unevenly spaced: 0, 2, 5, 8, 10
    beat_timestamps = [0.0, 2.0, 5.0, 8.0, 10.0]

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.8,
        cue_template=(CueTemplate("Near5", time_fraction=0.45),),
        total_duration_seconds=10.0,
    )

    # 0.45 * 10 = 4.5; nearest beat is 5.0 at index 2
    assert cues[0]["timestamp_seconds"] == 5.0
    assert cues[0]["beat_index"] == 2


def test_normalized_cue_template_rejects_invalid_time_fraction() -> None:
    with pytest.raises(ValueError, match="time_fraction must be between"):
        propose_cue_points(
            [0.0],
            beat_confidence=0.8,
            cue_template=(CueTemplate("Bad", time_fraction=1.1),),
        )

    with pytest.raises(ValueError, match="time_fraction must be between"):
        propose_cue_points(
            [0.0],
            beat_confidence=0.8,
            cue_template=(CueTemplate("Bad", time_fraction=-0.1),),
        )


def test_normalized_cue_template_rejects_missing_anchor() -> None:
    with pytest.raises(ValueError, match="beat_index or time_fraction"):
        propose_cue_points(
            [0.0],
            beat_confidence=0.8,
            cue_template=(CueTemplate("Ghost"),),
        )


def test_beat_analysis_result_includes_total_duration() -> None:
    result = BeatAnalysisResult(
        beat_timestamps=[0.0, 0.5, 1.0],
        beat_confidence=0.9,
        total_duration_seconds=180.0,
    )
    assert result.total_duration_seconds == 180.0


def test_propose_cue_points_performance_preset_with_duration() -> None:
    # 200 beats at 0.5s each → beat span 0–99.5s, total duration 100s
    beat_timestamps = [round(i * 0.5, 3) for i in range(200)]

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.9,
        cue_template=cue_template_for_preset("performance"),
        total_duration_seconds=100.0,
    )

    labels = [c["cue_label"] for c in cues]
    # All 5 beat-indexed cues fit (beats 0,8,16,32,64 all < 200)
    assert "Intro" in labels
    assert "8 Beats In" in labels
    assert "16 Beats In" in labels
    assert "32 Beats In" in labels
    assert "64 Beats In" in labels
    # All 3 time-fraction cues resolve
    assert "Mid" in labels
    assert "Last Chorus" in labels
    assert "Outro" in labels
    assert len(cues) == 8


def test_propose_cue_points_minimix_preset_with_duration() -> None:
    # 200 beats at 0.5s each → beat span 0–99.5s, total duration 100s
    beat_timestamps = [round(i * 0.5, 3) for i in range(200)]

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.85,
        cue_template=cue_template_for_preset("minimix"),
        total_duration_seconds=100.0,
    )

    labels = [c["cue_label"] for c in cues]
    assert labels[0] == "Track 1"
    assert "Track 2" in labels
    assert "Track 5" in labels
    assert "Track 8" in labels
    # All 8 minimix cues should be present (beat 0 is in range + 7 time-fraction)
    assert len(cues) == 8


def test_propose_cue_points_skips_time_fraction_with_no_nearby_beat() -> None:
    # Sparse beats: nearest to target 30s is at 10s — 20s away, exceeds 2.0s threshold
    beat_timestamps = [0.0, 10.0, 50.0]

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.8,
        cue_template=(CueTemplate(cue_label="Gap", time_fraction=0.30),),
        total_duration_seconds=100.0,
    )

    assert cues == []


def test_propose_cue_points_deduplicates_same_beat_index() -> None:
    # Two time-fraction cues that resolve to the same beat: second is skipped
    # beats at 1s intervals; target 50.0s and 50.4s both resolve to beat 50
    beat_timestamps = [float(i) for i in range(101)]

    cues = propose_cue_points(
        beat_timestamps,
        beat_confidence=0.8,
        cue_template=(
            CueTemplate(cue_label="A", time_fraction=0.500),
            CueTemplate(cue_label="B", time_fraction=0.504),
        ),
        total_duration_seconds=100.0,
    )

    # Both resolve to beat 50; only the first is kept
    assert len(cues) == 1
    assert cues[0]["cue_label"] == "A"
    assert cues[0]["beat_index"] == 50


def test_normalized_cue_template_rejects_both_anchors_set() -> None:
    with pytest.raises(ValueError, match="only one of beat_index or time_fraction"):
        propose_cue_points(
            [0.0],
            beat_confidence=0.8,
            cue_template=(CueTemplate(cue_label="Both", beat_index=0, time_fraction=0.5),),
        )


def test_parse_cue_template_produces_beat_index_only_cues() -> None:
    cues = parse_cue_template(["Intro=0", "Drop=32"])
    for cue in cues:
        assert cue.beat_index is not None
        assert cue.time_fraction is None
