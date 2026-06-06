from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from threading import Thread

import pytest

from dj_library_prep import database, local_api
from dj_library_prep.beat_analyzer import BeatCueAnalysisSummary, CueTemplate
from dj_library_prep.local_api import _handler_factory
from dj_library_prep.models import ReviewStatus, Track


def test_tracks_endpoint_filters_by_review_status(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    _save_track(
        db_path,
        Track(
            file_path="C:/Music/review.mp3",
            file_name="review.mp3",
            file_extension=".mp3",
            review_status=ReviewStatus.NEEDS_REVIEW,
        ),
    )
    _save_track(
        db_path,
        Track(
            file_path="C:/Music/approved.mp3",
            file_name="approved.mp3",
            file_extension=".mp3",
            review_status=ReviewStatus.APPROVED,
        ),
    )

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "GET", "/api/tracks?status=needs_review")

    assert status == 200
    assert [track["file_name"] for track in payload["tracks"]] == ["review.mp3"]


def test_patch_track_endpoint_updates_review_fields_and_history(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/song.mp3",
            file_name="song.mp3",
            file_extension=".mp3",
            normalized_primary_genre="Hip-Hop",
            review_status=ReviewStatus.NEEDS_REVIEW,
        ),
    )

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(
            server,
            "PATCH",
            f"/api/tracks/{saved_track['id']}",
            {
                "normalized_primary_genre": "Latin",
                "normalized_subgenre": "Salsa",
                "dj_use_tags": "latin;club",
                "review_status": "approved",
            },
        )
        history_status, history_payload = _request(
            server, "GET", f"/api/tracks/{saved_track['id']}/history"
        )

    assert status == 200
    assert payload["track"]["normalized_primary_genre"] == "Latin"
    assert payload["track"]["normalized_subgenre"] == "Salsa"
    assert payload["track"]["dj_use_tags"] == "latin;club"
    assert payload["track"]["review_status"] == "approved"

    assert history_status == 200
    assert len(history_payload["history"]) == 1
    assert history_payload["history"][0]["source"] == "user_edit"
    assert history_payload["history"][0]["action"] == "edit"
    assert history_payload["history"][0]["new_review_status"] == "approved"


def test_cue_points_endpoint_returns_stored_cues(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/song.mp3",
            file_name="song.mp3",
            file_extension=".mp3",
            artist="Artist",
            title="Song",
        ),
    )
    with database.connect(db_path) as connection:
        database.insert_missing_cue_points(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            cue_points=[
                {
                    "cue_label": "Load",
                    "beat_index": 0,
                    "timestamp_seconds": 0.0,
                    "cue_confidence": 0.8,
                    "review_status": "pending",
                }
            ],
        )
        connection.commit()

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "GET", "/api/cue-points")

    assert status == 200
    assert payload["cue_points"][0]["file_name"] == "song.mp3"
    assert payload["cue_points"][0]["artist"] == "Artist"
    assert payload["cue_points"][0]["cue_label"] == "Load"


def test_analyze_beats_endpoint_passes_ui_cue_template(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    captured = {}

    def fake_analyze_beats_for_folder(folder, database_path, cue_template):
        captured["folder"] = folder
        captured["database_path"] = database_path
        captured["cue_template"] = cue_template
        return BeatCueAnalysisSummary(
            total_files=1,
            analyzed_tracks=1,
            stored_beats=40,
            proposed_cue_points=2,
            cue_points_needing_review=0,
            failed_tracks=0,
        )

    monkeypatch.setattr(
        local_api,
        "analyze_beats_for_folder",
        fake_analyze_beats_for_folder,
    )

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(
            server,
            "POST",
            "/api/analyze-beats",
            {
                "folder": "C:/Music",
                "cue_preset": "starter",
                "cues": ["Load=0", "Drop Prep=32"],
            },
        )

    assert status == 200
    assert captured == {
        "folder": "C:/Music",
        "database_path": db_path,
        "cue_template": (
            CueTemplate("Load", 0),
            CueTemplate("Drop Prep", 32),
        ),
    }
    assert payload["summary"]["inserted_cue_points"] == 2
    assert payload["summary"]["stored_beats"] == 40


def test_patch_cue_point_renames_label(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/song.mp3",
            file_name="song.mp3",
            file_extension=".mp3",
        ),
    )
    with database.connect(db_path) as connection:
        database.insert_missing_cue_points(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            cue_points=[
                {
                    "cue_label": "Intro",
                    "beat_index": 0,
                    "timestamp_seconds": 0.0,
                    "cue_confidence": 0.8,
                    "review_status": "pending",
                }
            ],
        )
        connection.commit()
        cue = database.list_cue_points(connection)[0]

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(
            server,
            "PATCH",
            f"/api/cue-points/{cue['id']}",
            {"cue_label": "Drop"},
        )

    assert status == 200
    assert payload["cue_point"]["cue_label"] == "Drop"
    assert payload["cue_point"]["id"] == cue["id"]
    assert payload["cue_point"]["beat_index"] == 0

    with database.connect(db_path) as connection:
        updated = database.list_cue_points(connection)[0]
    assert updated["cue_label"] == "Drop"


def test_patch_cue_point_rejects_empty_label(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/song.mp3",
            file_name="song.mp3",
            file_extension=".mp3",
        ),
    )
    with database.connect(db_path) as connection:
        database.insert_missing_cue_points(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            cue_points=[
                {
                    "cue_label": "Intro",
                    "beat_index": 0,
                    "timestamp_seconds": 0.0,
                    "cue_confidence": 0.8,
                    "review_status": "pending",
                }
            ],
        )
        connection.commit()
        cue = database.list_cue_points(connection)[0]

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(
            server,
            "PATCH",
            f"/api/cue-points/{cue['id']}",
            {"cue_label": "   "},
        )

    assert status == 400
    assert "empty" in payload["error"].lower()

    with database.connect(db_path) as connection:
        unchanged = database.list_cue_points(connection)[0]
    assert unchanged["cue_label"] == "Intro"


def test_pads_endpoints_autofill_rename_and_recapture(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/song.mp3",
            file_name="song.mp3",
            file_extension=".mp3",
        ),
    )
    with database.connect(db_path) as connection:
        database.replace_beat_timestamps(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            beat_timestamps=[round(i * 0.5, 3) for i in range(300)],
            beat_confidence=0.8,
        )
        connection.commit()

    track_id = saved_track["id"]
    with _running_api(db_path, frontend_dir) as server:
        empty_status, empty_payload = _request(
            server, "GET", f"/api/tracks/{track_id}/pads"
        )
        fill_status, fill_payload = _request(
            server, "POST", f"/api/tracks/{track_id}/pads/auto-fill", {}
        )
        rename_status, rename_payload = _request(
            server, "PUT", f"/api/tracks/{track_id}/pads/1", {"label": "Drop"}
        )
        recapture_status, recapture_payload = _request(
            server,
            "PUT",
            f"/api/tracks/{track_id}/pads/2",
            {"timestamp_seconds": 41.5},
        )

    assert empty_status == 200
    assert len(empty_payload["pads"]) == 8
    assert all(pad["timestamp_seconds"] is None for pad in empty_payload["pads"])

    assert fill_status == 200
    assert fill_payload["pads"][0]["timestamp_seconds"] == 0.0
    assert fill_payload["pads"][1]["timestamp_seconds"] == 16.0

    assert rename_status == 200
    assert rename_payload["pad"]["label"] == "Drop"
    assert rename_payload["pad"]["timestamp_seconds"] == 16.0

    assert recapture_status == 200
    assert recapture_payload["pad"]["timestamp_seconds"] == 41.5
    assert recapture_payload["pad"]["source"] == "manual"


def test_pads_autofill_without_beats_returns_400(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/song.mp3",
            file_name="song.mp3",
            file_extension=".mp3",
        ),
    )

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(
            server, "POST", f"/api/tracks/{saved_track['id']}/pads/auto-fill", {}
        )

    assert status == 400
    assert "beats" in payload["error"].lower()


def test_audio_endpoint_serves_file_bytes(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    audio_path = tmp_path / "song.mp3"
    audio_bytes = b"ID3 fake audio bytes"
    audio_path.write_bytes(audio_bytes)

    from urllib.parse import quote

    with _running_api(db_path, frontend_dir) as server:
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        connection.request("GET", f"/api/audio?path={quote(str(audio_path))}")
        response = connection.getresponse()
        body = response.read()
        content_type = response.getheader("Content-Type")
        connection.close()

    assert response.status == 200
    assert body == audio_bytes
    assert content_type == "audio/mpeg"


def test_audio_endpoint_rejects_missing_file(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    from urllib.parse import quote

    with _running_api(db_path, frontend_dir) as server:
        missing = tmp_path / "nope.mp3"
        status, payload = _request(
            server, "GET", f"/api/audio?path={quote(str(missing))}"
        )

    assert status == 404


def test_per_track_analyze_beats_detects_and_fills_pads(tmp_path, monkeypatch) -> None:
    from dj_library_prep.beat_analyzer import BeatAnalysisResult

    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/song.mp3",
            file_name="song.mp3",
            file_extension=".mp3",
        ),
    )

    monkeypatch.setattr(
        local_api,
        "detect_beat_timestamps",
        lambda path: BeatAnalysisResult(
            beat_timestamps=[round(i * 0.5, 3) for i in range(300)],
            beat_confidence=0.8,
        ),
    )

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(
            server, "POST", f"/api/tracks/{saved_track['id']}/analyze-beats"
        )

    assert status == 200
    assert payload["stored_beats"] == 300
    assert payload["pads"][0]["timestamp_seconds"] == 0.0
    assert payload["pads"][1]["timestamp_seconds"] == 16.0


def test_per_track_analyze_beats_preserves_on_failure(tmp_path, monkeypatch) -> None:
    from dj_library_prep.beat_analyzer import BeatAnalysisResult

    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/song.mp3",
            file_name="song.mp3",
            file_extension=".mp3",
        ),
    )
    with database.connect(db_path) as connection:
        database.replace_beat_timestamps(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            beat_timestamps=[float(i) for i in range(40)],
            beat_confidence=0.8,
        )
        connection.commit()

    monkeypatch.setattr(
        local_api,
        "detect_beat_timestamps",
        lambda path: BeatAnalysisResult(beat_timestamps=[], beat_confidence=0.0),
    )

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(
            server, "POST", f"/api/tracks/{saved_track['id']}/analyze-beats"
        )

    assert status == 400
    with database.connect(db_path) as connection:
        beats = database.list_beat_timestamps(connection)
    assert len(beats) == 40  # preserved


def test_clear_all_pads_endpoint(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/song.mp3",
            file_name="song.mp3",
            file_extension=".mp3",
        ),
    )
    track_id = saved_track["id"]
    with database.connect(db_path) as connection:
        database.replace_beat_timestamps(
            connection,
            track_id=track_id,
            file_path=saved_track["file_path"],
            beat_timestamps=[round(i * 0.5, 3) for i in range(300)],
            beat_confidence=0.8,
        )
        connection.commit()

    with _running_api(db_path, frontend_dir) as server:
        _request(server, "POST", f"/api/tracks/{track_id}/pads/auto-fill", {})
        status, payload = _request(server, "DELETE", f"/api/tracks/{track_id}/pads")

    assert status == 200
    assert len(payload["pads"]) == 8
    assert all(pad["timestamp_seconds"] is None for pad in payload["pads"])


def test_beats_endpoint_returns_stored_beats(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/song.mp3",
            file_name="song.mp3",
            file_extension=".mp3",
        ),
    )
    with database.connect(db_path) as connection:
        database.replace_beat_timestamps(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            beat_timestamps=[0.0, 0.5, 1.0, 1.5, 2.0],
            beat_confidence=0.82,
        )
        connection.commit()

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "GET", f"/api/tracks/{saved_track['id']}/beats")

    assert status == 200
    assert payload["beats"] == [0.0, 0.5, 1.0, 1.5, 2.0]
    assert payload["beat_confidence"] == 0.82


def test_beats_endpoint_returns_empty_for_track_without_beats(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/no-beats.mp3",
            file_name="no-beats.mp3",
            file_extension=".mp3",
        ),
    )

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "GET", f"/api/tracks/{saved_track['id']}/beats")

    assert status == 200
    assert payload["beats"] == []
    assert payload["beat_confidence"] == 0.0


def test_beats_endpoint_returns_exact_stored_confidence(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    saved_track = _save_track(
        db_path,
        Track(
            file_path="C:/Music/confident.mp3",
            file_name="confident.mp3",
            file_extension=".mp3",
        ),
    )
    with database.connect(db_path) as connection:
        database.replace_beat_timestamps(
            connection,
            track_id=saved_track["id"],
            file_path=saved_track["file_path"],
            beat_timestamps=[0.0, 0.25, 0.5],
            beat_confidence=0.95,
        )
        connection.commit()

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "GET", f"/api/tracks/{saved_track['id']}/beats")

    assert status == 200
    assert payload["beat_confidence"] == 0.95
    assert len(payload["beats"]) == 3


@contextmanager
def _running_api(database_path, frontend_dir):
    handler = _handler_factory(frontend_dir, database_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _request(server, method: str, path: str, payload: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    raw_body = response.read().decode("utf-8")
    connection.close()
    return response.status, json.loads(raw_body)


def _save_track(db_path, track: Track):
    with database.connect(db_path) as connection:
        database.save_tracks(connection, [track])
        return database.get_track_by_file_path(connection, track.file_path)


# ---- Part B: bulk update API tests (session 7) ----

def test_bulk_update_approves_selected_tracks(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    t1 = _save_track(db_path, Track(file_path="C:/Music/a.mp3", file_name="a.mp3", file_extension=".mp3", review_status=ReviewStatus.NEEDS_REVIEW))
    t2 = _save_track(db_path, Track(file_path="C:/Music/b.mp3", file_name="b.mp3", file_extension=".mp3", review_status=ReviewStatus.NEEDS_REVIEW))

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "POST", "/api/tracks/bulk-update", {"track_ids": [t1["id"], t2["id"]], "review_status": "approved"})

    assert status == 200
    assert payload["updated"] == 2
    with database.connect(db_path) as connection:
        assert database.get_track_by_id(connection, t1["id"])["review_status"] == "approved"
        assert database.get_track_by_id(connection, t2["id"])["review_status"] == "approved"


def test_bulk_update_empty_track_ids_returns_400(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "POST", "/api/tracks/bulk-update", {"track_ids": [], "review_status": "approved"})

    assert status == 400
    assert "No tracks selected" in payload["error"]


def test_bulk_update_invalid_review_status_returns_400(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    t1 = _save_track(db_path, Track(file_path="C:/Music/c.mp3", file_name="c.mp3", file_extension=".mp3"))

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "POST", "/api/tracks/bulk-update", {"track_ids": [t1["id"]], "review_status": "edited"})

    assert status == 400


def test_bulk_update_skips_tracks_already_at_target_status(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    t1 = _save_track(db_path, Track(file_path="C:/Music/d.mp3", file_name="d.mp3", file_extension=".mp3", review_status=ReviewStatus.APPROVED))
    t2 = _save_track(db_path, Track(file_path="C:/Music/e.mp3", file_name="e.mp3", file_extension=".mp3", review_status=ReviewStatus.NEEDS_REVIEW))

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "POST", "/api/tracks/bulk-update", {"track_ids": [t1["id"], t2["id"]], "review_status": "approved"})

    assert status == 200
    assert payload["updated"] == 1
    assert payload["skipped"] == 1


def test_bulk_update_skips_nonexistent_track_ids(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    t1 = _save_track(db_path, Track(file_path="C:/Music/f.mp3", file_name="f.mp3", file_extension=".mp3", review_status=ReviewStatus.NEEDS_REVIEW))

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "POST", "/api/tracks/bulk-update", {"track_ids": [t1["id"], 99999], "review_status": "approved"})

    assert status == 200
    assert payload["updated"] == 1
    assert payload["not_found"] == 1


def test_bulk_approve_creates_review_history_with_bulk_action_source(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    t1 = _save_track(db_path, Track(file_path="C:/Music/g.mp3", file_name="g.mp3", file_extension=".mp3", review_status=ReviewStatus.NEEDS_REVIEW))

    with _running_api(db_path, frontend_dir) as server:
        _request(server, "POST", "/api/tracks/bulk-update", {"track_ids": [t1["id"]], "review_status": "approved"})
        _, history_payload = _request(server, "GET", f"/api/tracks/{t1['id']}/history")

    history = history_payload["history"]
    assert len(history) == 1
    assert history[0]["source"] == "bulk_action"
    assert history[0]["action"] == "bulk_approve"


# ---- batch auto-fill API tests ----

def _track_with_beats_api(db_path, file_path="C:/Music/api_beats.mp3", beat_count=100):
    from dj_library_prep import database
    track = Track(file_path=file_path, file_name=file_path.split("/")[-1], file_extension=".mp3")
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
    return saved


def test_batch_auto_fill_endpoint_fills_tracks(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    _track_with_beats_api(db_path)

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "POST", "/api/pads/batch-auto-fill",
                                   {"phrase_length": 32, "skip_existing": True})

    assert status == 200
    s = payload["summary"]
    assert s["filled"] == 1
    assert s["skipped_no_beats"] == 0


def test_batch_auto_fill_endpoint_skips_tracks_with_existing_pads(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    saved = _track_with_beats_api(db_path)

    from dj_library_prep import pads as pad_service
    pad_service.autofill_pads(saved["id"], database_path=db_path)

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "POST", "/api/pads/batch-auto-fill",
                                   {"skip_existing": True})

    assert status == 200
    s = payload["summary"]
    assert s["skipped_existing_pads"] == 1
    assert s["filled"] == 0


def test_batch_auto_fill_endpoint_invalid_phrase_length_returns_400(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "POST", "/api/pads/batch-auto-fill",
                                   {"phrase_length": 0})

    assert status == 400
    assert "error" in payload


def test_auto_fill_with_nudge_applies_offset(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    saved = _track_with_beats_api(db_path, beat_count=300)

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "POST",
            f"/api/tracks/{saved['id']}/pads/auto-fill",
            {"nudge_seconds": 0.05})

    assert status == 200
    pads = payload["pads"]
    assert pads[0]["timestamp_seconds"] == pytest.approx(0.05)


def test_auto_fill_without_nudge_uses_exact_timestamps(tmp_path) -> None:
    db_path = tmp_path / "tracks.sqlite3"
    frontend_dir = tmp_path / "frontend"
    frontend_dir.mkdir()
    saved = _track_with_beats_api(db_path, beat_count=300)

    with _running_api(db_path, frontend_dir) as server:
        status, payload = _request(server, "POST",
            f"/api/tracks/{saved['id']}/pads/auto-fill", {})

    assert status == 200
    pads = payload["pads"]
    assert pads[0]["timestamp_seconds"] == 0.0
