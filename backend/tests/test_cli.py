from dj_library_prep import cli
from dj_library_prep.beat_analyzer import BeatCueAnalysisSummary, CueTemplate


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
