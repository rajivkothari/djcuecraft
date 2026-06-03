from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from threading import Thread

from dj_library_prep import database
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
    assert history_payload["history"][0]["source"] == "review_ui"
    assert history_payload["history"][0]["new_review_status"] == "approved"


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
