from dj_library_prep import database
from dj_library_prep import bpm_analyzer
from dj_library_prep.bpm_analyzer import BpmResult, analyze_bpm_for_folder
from dj_library_prep.models import ReviewStatus, Track


def test_analyze_bpm_updates_sqlite_only_and_preserves_high_confidence_status(
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

    monkeypatch.setattr(
        bpm_analyzer,
        "detect_bpm",
        lambda path: BpmResult(bpm=124.0, confidence=0.82),
    )

    summary = analyze_bpm_for_folder(music_dir, db_path)

    assert summary.total_files == 1
    assert summary.analyzed_tracks == 1
    assert summary.tracks_needing_review == 0
    assert summary.failed_tracks == 0

    with database.connect(db_path) as connection:
        updated = database.list_tracks(connection)[0]

    assert updated["bpm"] == 124.0
    assert updated["bpm_confidence"] == 0.82
    assert updated["review_status"] == "pending"
    assert audio_path.read_bytes() == b"not real audio"


def test_analyze_bpm_marks_low_confidence_results_needs_review(
    tmp_path, monkeypatch
) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    audio_path = music_dir / "low-confidence.mp3"
    audio_path.write_bytes(b"not real audio")
    db_path = tmp_path / "tracks.sqlite3"

    monkeypatch.setattr(
        bpm_analyzer,
        "detect_bpm",
        lambda path: BpmResult(bpm=96.0, confidence=0.31),
    )

    summary = analyze_bpm_for_folder(music_dir, db_path)

    assert summary.tracks_needing_review == 1
    with database.connect(db_path) as connection:
        updated = database.list_tracks(connection)[0]

    assert updated["bpm"] == 96.0
    assert updated["bpm_confidence"] == 0.31
    assert updated["review_status"] == "needs_review"


def test_analyze_bpm_skips_approved_tracks_without_force(
    tmp_path, monkeypatch
) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    audio_path = music_dir / "approved.mp3"
    audio_path.write_bytes(b"not real audio")
    db_path = tmp_path / "tracks.sqlite3"

    track = Track(
        file_path=str(audio_path),
        file_name=audio_path.name,
        file_extension=".mp3",
        bpm=128.0,
        bpm_confidence=0.95,
        review_status=ReviewStatus.APPROVED,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    called = []
    monkeypatch.setattr(
        bpm_analyzer,
        "detect_bpm",
        lambda path: called.append(path) or BpmResult(bpm=64.0, confidence=0.9),
    )

    summary = analyze_bpm_for_folder(music_dir, db_path)

    assert called == [], "detect_bpm must not be called for approved tracks"
    assert summary.skipped_reviewed_tracks == 1
    assert summary.analyzed_tracks == 0

    with database.connect(db_path) as connection:
        row = database.list_tracks(connection)[0]
    assert row["bpm"] == 128.0, "BPM must be unchanged for approved track"
    assert row["bpm_confidence"] == 0.95


def test_analyze_bpm_skips_edited_tracks_without_force(
    tmp_path, monkeypatch
) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    audio_path = music_dir / "edited.mp3"
    audio_path.write_bytes(b"not real audio")
    db_path = tmp_path / "tracks.sqlite3"

    track = Track(
        file_path=str(audio_path),
        file_name=audio_path.name,
        file_extension=".mp3",
        bpm=100.0,
        bpm_confidence=0.8,
        review_status=ReviewStatus.EDITED,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    monkeypatch.setattr(
        bpm_analyzer, "detect_bpm", lambda path: BpmResult(bpm=50.0, confidence=0.9)
    )

    summary = analyze_bpm_for_folder(music_dir, db_path)

    assert summary.skipped_reviewed_tracks == 1
    with database.connect(db_path) as connection:
        row = database.list_tracks(connection)[0]
    assert row["bpm"] == 100.0


def test_analyze_bpm_force_overwrites_approved_track(
    tmp_path, monkeypatch
) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    audio_path = music_dir / "approved.mp3"
    audio_path.write_bytes(b"not real audio")
    db_path = tmp_path / "tracks.sqlite3"

    track = Track(
        file_path=str(audio_path),
        file_name=audio_path.name,
        file_extension=".mp3",
        bpm=128.0,
        bpm_confidence=0.95,
        review_status=ReviewStatus.APPROVED,
    )
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])

    monkeypatch.setattr(
        bpm_analyzer, "detect_bpm", lambda path: BpmResult(bpm=64.0, confidence=0.9)
    )

    summary = analyze_bpm_for_folder(music_dir, db_path, force=True)

    assert summary.skipped_reviewed_tracks == 0
    assert summary.analyzed_tracks == 1
    with database.connect(db_path) as connection:
        row = database.list_tracks(connection)[0]
    assert row["bpm"] == 64.0


def test_analyze_bpm_still_processes_pending_and_needs_review_tracks(
    tmp_path, monkeypatch
) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    for name in ("pending.mp3", "needs_review.mp3"):
        (music_dir / name).write_bytes(b"not real audio")
    db_path = tmp_path / "tracks.sqlite3"

    tracks = [
        Track(
            file_path=str(music_dir / "pending.mp3"),
            file_name="pending.mp3",
            file_extension=".mp3",
            review_status=ReviewStatus.PENDING,
        ),
        Track(
            file_path=str(music_dir / "needs_review.mp3"),
            file_name="needs_review.mp3",
            file_extension=".mp3",
            review_status=ReviewStatus.NEEDS_REVIEW,
        ),
    ]
    with database.connect(db_path) as connection:
        database.save_tracks(connection, tracks)

    monkeypatch.setattr(
        bpm_analyzer, "detect_bpm", lambda path: BpmResult(bpm=120.0, confidence=0.8)
    )

    summary = analyze_bpm_for_folder(music_dir, db_path)

    assert summary.analyzed_tracks == 2
    assert summary.skipped_reviewed_tracks == 0


def test_database_migrates_legacy_tracks_table_with_bpm_columns(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    with database.connect(db_path) as connection:
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(tracks)")}

    assert "bpm" in columns
    assert "bpm_confidence" in columns
