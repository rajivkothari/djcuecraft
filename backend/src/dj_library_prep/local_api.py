from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dj_library_prep import database
from dj_library_prep.beat_analyzer import (
    CUE_PRESETS,
    DEFAULT_CUE_PRESET,
    CueTemplate,
    analyze_beats_for_folder,
    cue_template_for_preset,
    parse_cue_template,
)
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
            if parsed.path == "/api/cue-points":
                self._write_json({"cue_points": _list_cue_points(database_path)})
                return
            if parsed.path == "/api/cue-presets":
                self._write_json(
                    {
                        "presets": sorted(CUE_PRESETS),
                        "default_preset": DEFAULT_CUE_PRESET,
                    }
                )
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

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/analyze-beats":
                try:
                    payload = self._read_json()
                    folder = str(payload.get("folder", "")).strip()
                    if not folder:
                        raise ValueError("Music folder is required.")

                    cue_template = _cue_template_from_payload(payload)
                    summary = analyze_beats_for_folder(
                        folder,
                        database_path,
                        cue_template,
                    )
                except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
                    self._write_json({"error": str(exc)}, status=400)
                    return

                self._write_json(
                    {
                        "summary": {
                            "total_files": summary.total_files,
                            "analyzed_tracks": summary.analyzed_tracks,
                            "stored_beats": summary.stored_beats,
                            "inserted_cue_points": summary.proposed_cue_points,
                            "cue_points_needing_review": summary.cue_points_needing_review,
                            "failed_tracks": summary.failed_tracks,
                        },
                        "cue_points": _list_cue_points(database_path),
                    }
                )
                return

            self._write_json({"error": "Not found"}, status=404)

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
            if len(parts) == 3 and parts[:2] == ["api", "cue-points"]:
                try:
                    cue_id = int(parts[2])
                    payload = self._read_json()
                    new_label = str(payload.get("cue_label", "")).strip()
                    if not new_label:
                        raise ValueError("cue_label must not be empty.")
                    with database.connect(database_path) as connection:
                        updated = database.update_cue_label(connection, cue_id, new_label)
                    if updated is None:
                        self._write_json({"error": "Cue point not found."}, status=404)
                        return
                except (ValueError, json.JSONDecodeError) as exc:
                    self._write_json({"error": str(exc)}, status=400)
                    return
                self._write_json({"cue_point": dict(updated)})
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


def _cue_template_from_payload(payload: dict) -> tuple[CueTemplate, ...]:
    cue_specs = [str(cue) for cue in payload.get("cues", []) if str(cue).strip()]
    if cue_specs:
        return parse_cue_template(cue_specs)

    preset_name = str(payload.get("cue_preset", DEFAULT_CUE_PRESET) or DEFAULT_CUE_PRESET)
    return cue_template_for_preset(preset_name)


def _list_cue_points(database_path: Path) -> list[dict]:
    with database.connect(database_path) as connection:
        return [dict(row) for row in database.list_cue_points(connection)]
