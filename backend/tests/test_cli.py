from dj_library_prep import cli, database
from dj_library_prep.beat_analyzer import BeatCueAnalysisSummary, CueTemplate
from dj_library_prep.models import Track


def test_scan_folder_records_minimal_track_when_metadata_read_fails(
    tmp_path, monkeypatch
) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    audio_path = music_dir / "bad.mp3"
    audio_path.write_bytes(b"not real audio")
    db_path = tmp_path / "tracks.sqlite3"

    def broken_read_track_metadata(path):
        raise RuntimeError("metadata read failed")

    monkeypatch.setattr(cli, "read_track_metadata", broken_read_track_metadata)

    summary = cli.scan_folder(music_dir, db_path)

    assert summary.total_tracks_scanned == 1
    assert summary.failed_tracks == 1
    assert summary.tracks_needing_review == 1

    with database.connect(db_path) as connection:
        rows = database.list_tracks(connection)

    assert len(rows) == 1
    assert rows[0]["file_path"] == str(audio_path)
    assert rows[0]["file_name"] == "bad.mp3"
    assert rows[0]["file_extension"] == ".mp3"
    assert rows[0]["review_status"] == "needs_review"


def test_scan_folder_stores_metadata_suggestions_without_touching_audio_file(
    tmp_path, monkeypatch
) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    audio_path = music_dir / "club.mp3"
    original_bytes = b"not real audio"
    audio_path.write_bytes(original_bytes)
    db_path = tmp_path / "tracks.sqlite3"

    def fake_read_track_metadata(path):
        return Track(
            file_path=str(path),
            file_name=path.name,
            file_extension=path.suffix,
            artist="Artist",
            title="Club Rap Anthem",
            album="Promo",
            year="2004",
            original_genre="Hip-Hop/Rap",
            metadata_confidence=1.0,
        )

    monkeypatch.setattr(cli, "read_track_metadata", fake_read_track_metadata)

    summary = cli.scan_folder(music_dir, db_path)

    assert summary.total_tracks_scanned == 1
    with database.connect(db_path) as connection:
        rows = database.list_tracks(connection)

    assert rows[0]["normalized_decade"] == "00s"
    assert rows[0]["normalized_primary_genre"] == "Hip-Hop"
    assert rows[0]["normalized_subgenre"] == "Club Rap"
    assert rows[0]["genre_confidence"] >= 0.9
    assert rows[0]["review_status"] == "pending"
    assert audio_path.read_bytes() == original_bytes


def test_analyze_beats_command_passes_custom_cue_template(monkeypatch) -> None:
    captured = {}

    def fake_analyze_beats_for_folder(folder, database_path, cue_template):
        captured["folder"] = folder
        captured["database_path"] = database_path
        captured["cue_template"] = cue_template
        return BeatCueAnalysisSummary(
            total_files=0,
            analyzed_tracks=0,
            stored_beats=0,
            proposed_cue_points=0,
            cue_points_needing_review=0,
            failed_tracks=0,
        )

    monkeypatch.setattr(
        cli,
        "analyze_beats_for_folder",
        fake_analyze_beats_for_folder,
    )

    exit_code = cli.main(
        [
            "analyze-beats",
            "C:/Music",
            "--database",
            "tracks.sqlite3",
            "--cue",
            "Load=0",
            "--cue",
            "Drop Prep=32",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "folder": "C:/Music",
        "database_path": "tracks.sqlite3",
        "cue_template": (
            CueTemplate("Load", 0),
            CueTemplate("Drop Prep", 32),
        ),
    }


def test_export_csv_refuses_to_overwrite_existing_file_without_flag(
    tmp_path, monkeypatch
) -> None:
    existing = tmp_path / "approved.csv"
    existing.write_text("old content", encoding="utf-8")

    called = []
    monkeypatch.setattr(cli, "export_tracks_to_csv", lambda db, out: called.append(out) or 0)

    exit_code = cli.main(
        ["export-csv", "--database", "tracks.sqlite3", "--output", str(existing)]
    )

    assert exit_code == 1
    assert called == [], "exporter must not be called when output exists and --overwrite not set"
    assert existing.read_text(encoding="utf-8") == "old content"


def test_export_csv_overwrites_existing_file_with_flag(
    tmp_path, monkeypatch
) -> None:
    existing = tmp_path / "approved.csv"
    existing.write_text("old content", encoding="utf-8")

    monkeypatch.setattr(cli, "export_tracks_to_csv", lambda db, out: 3)

    exit_code = cli.main(
        [
            "export-csv",
            "--database", "tracks.sqlite3",
            "--output", str(existing),
            "--overwrite",
        ]
    )

    assert exit_code == 0


def test_export_json_refuses_to_overwrite_existing_file_without_flag(
    tmp_path, monkeypatch
) -> None:
    existing = tmp_path / "approved.json"
    existing.write_text("{}", encoding="utf-8")

    called = []
    monkeypatch.setattr(
        cli, "export_approved_tracks_to_json", lambda db, out: called.append(out) or 0
    )

    exit_code = cli.main(
        ["export-json", "--database", "tracks.sqlite3", "--output", str(existing)]
    )

    assert exit_code == 1
    assert called == []


def test_export_json_command_uses_safe_metadata_export(monkeypatch) -> None:
    captured = {}

    def fake_export(database_path, output_path):
        captured["database_path"] = database_path
        captured["output_path"] = output_path
        return 2

    monkeypatch.setattr(cli, "export_approved_tracks_to_json", fake_export)

    exit_code = cli.main(
        [
            "export-json",
            "--database",
            "tracks.sqlite3",
            "--output",
            "approved.json",
        ]
    )

    assert exit_code == 0
    assert captured == {
        "database_path": "tracks.sqlite3",
        "output_path": "approved.json",
    }
