from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dj_library_prep.review_service import (
    list_review_history,
    list_review_tracks,
    update_review_track,
)


DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


def serve_ui(
    database_path: str | Path = "djcuecraft.sqlite3",
    host: str = "127.0.0.1",
    port: int = 8765,
    frontend_dir: str | Path = DEFAULT_FRONTEND_DIR,
) -> None:
    handler = _handler_factory(Path(frontend_dir), Path(database_path))
    server = ThreadingHTTPServer((host, port), handler)
    print(f"DJ CueCraft review UI: http://{host}:{port}")
    print("No audio files will be modified.")
    server.serve_forever()


def _handler_factory(frontend_dir: Path, database_path: Path):
    class ReviewRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(frontend_dir), **kwargs)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/tracks":
                query = parse_qs(parsed.query)
                status = query.get("status", [None])[0]
                tracks = list_review_tracks(database_path, review_status=status)
                self._write_json({"tracks": tracks})
                return
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "tracks"] and parts[3] == "history":
                try:
                    track_id = int(parts[2])
                    history = list_review_history(track_id, database_path)
                except ValueError as exc:
                    self._write_json({"error": str(exc)}, status=400)
                    return
                self._write_json({"history": history})
                return
            super().do_GET()

        def do_PATCH(self) -> None:
            parsed = urlparse(self.path)
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["api", "tracks"]:
                try:
                    track_id = int(parts[2])
                    payload = self._read_json()
                    track = update_review_track(track_id, payload, database_path)
                except KeyError as exc:
                    self._write_json({"error": str(exc)}, status=404)
                    return
                except (ValueError, json.JSONDecodeError) as exc:
                    self._write_json({"error": str(exc)}, status=400)
                    return
                self._write_json({"track": track})
                return
            self._write_json({"error": "Not found"}, status=404)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")
            return json.loads(raw_body or "{}")

        def _write_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            return

    return ReviewRequestHandler
