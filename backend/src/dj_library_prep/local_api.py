from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qs, urlparse

from dj_library_prep import database
from dj_library_prep.beat_analyzer import (
    CUE_PRESETS,
    DEFAULT_CUE_PRESET,
    CueTemplate,
    analyze_beats_for_folder,
    cue_template_for_preset,
    detect_beat_timestamps,
    parse_cue_template,
)
from dj_library_prep.review_service import (
    list_review_history,
    list_review_tracks,
    update_review_track,
)
from dj_library_prep import pads as pad_service
from dj_library_prep.models import SUPPORTED_EXTENSIONS


DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"

AUDIO_CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
}


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
            if parsed.path == "/api/browse-folder":
                self._write_json({"folder": _browse_for_folder()})
                return
            if parsed.path == "/api/audio":
                query = parse_qs(parsed.query)
                self._serve_audio(query.get("path", [""])[0])
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
            if len(parts) == 4 and parts[:2] == ["api", "tracks"] and parts[3] == "pads":
                try:
                    track_id = int(parts[2])
                    pads = pad_service.list_pads_for_track(track_id, database_path)
                except ValueError as exc:
                    self._write_json({"error": str(exc)}, status=400)
                    return
                self._write_json({"pads": pads})
                return
            if len(parts) == 4 and parts[:2] == ["api", "tracks"] and parts[3] == "beats":
                try:
                    track_id = int(parts[2])
                except ValueError:
                    self._write_json({"error": "Invalid track ID"}, status=400)
                    return
                self._write_json(_list_beats_for_track(database_path, track_id))
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

            parts = parsed.path.strip("/").split("/")
            if (
                len(parts) == 4
                and parts[:2] == ["api", "tracks"]
                and parts[3] == "analyze-beats"
            ):
                try:
                    track_id = int(parts[2])
                    result = _analyze_beats_for_track(database_path, track_id)
                except KeyError as exc:
                    self._write_json({"error": str(exc)}, status=404)
                    return
                except (RuntimeError, ValueError, OSError) as exc:
                    self._write_json({"error": str(exc)}, status=400)
                    return
                self._write_json(result)
                return
            if (
                len(parts) == 5
                and parts[:2] == ["api", "tracks"]
                and parts[3] == "pads"
                and parts[4] == "auto-fill"
            ):
                try:
                    track_id = int(parts[2])
                    payload = self._read_json()
                    phrase_length = int(
                        payload.get("phrase_length", pad_service.DEFAULT_PHRASE_LENGTH)
                    )
                    preset_name = payload.get("preset") or None
                    raw_duration = payload.get("total_duration_seconds")
                    total_duration_seconds = float(raw_duration) if raw_duration else None
                    pads = pad_service.autofill_pads(
                        track_id,
                        phrase_length=phrase_length,
                        preset_name=preset_name,
                        total_duration_seconds=total_duration_seconds,
                        database_path=database_path,
                    )
                except (ValueError, json.JSONDecodeError) as exc:
                    self._write_json({"error": str(exc)}, status=400)
                    return
                self._write_json({"pads": pads})
                return

            self._write_json({"error": "Not found"}, status=404)

        def do_PUT(self) -> None:
            parsed = urlparse(self.path)
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 5 and parts[:2] == ["api", "tracks"] and parts[3] == "pads":
                try:
                    track_id = int(parts[2])
                    pad_index = int(parts[4])
                    payload = self._read_json()
                    pad = pad_service.set_pad(
                        track_id,
                        pad_index,
                        label=payload.get("label"),
                        timestamp_seconds=payload.get("timestamp_seconds"),
                        beat_index=payload.get("beat_index"),
                        database_path=database_path,
                    )
                except (ValueError, json.JSONDecodeError) as exc:
                    self._write_json({"error": str(exc)}, status=400)
                    return
                self._write_json({"pad": pad})
                return
            self._write_json({"error": "Not found"}, status=404)

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 5 and parts[:2] == ["api", "tracks"] and parts[3] == "pads":
                try:
                    track_id = int(parts[2])
                    pad_index = int(parts[4])
                    pad_service.clear_pad(track_id, pad_index, database_path)
                except ValueError as exc:
                    self._write_json({"error": str(exc)}, status=400)
                    return
                self._write_json({"cleared": True})
                return
            if len(parts) == 4 and parts[:2] == ["api", "tracks"] and parts[3] == "pads":
                try:
                    track_id = int(parts[2])
                    pads = pad_service.clear_all_pads(track_id, database_path)
                except ValueError as exc:
                    self._write_json({"error": str(exc)}, status=400)
                    return
                self._write_json({"pads": pads})
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

        def _serve_audio(self, raw_path: str) -> None:
            if not raw_path:
                self._write_json({"error": "Audio path is required."}, status=400)
                return
            audio_path = Path(raw_path).expanduser()
            if audio_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                self._write_json({"error": "Unsupported audio type."}, status=400)
                return
            if not audio_path.is_file():
                self._write_json({"error": "Audio file not found."}, status=404)
                return

            try:
                data = audio_path.read_bytes()
            except OSError as exc:
                self._write_json({"error": str(exc)}, status=500)
                return

            content_type = AUDIO_CONTENT_TYPES.get(
                audio_path.suffix.lower(), "application/octet-stream"
            )
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Accept-Ranges", "none")
            self.end_headers()
            self.wfile.write(data)

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


def _list_beats_for_track(database_path: Path, track_id: int) -> dict:
    with database.connect(database_path) as connection:
        beats = database.list_beat_timestamps_for_track(connection, track_id)
        if not beats:
            return {"beats": [], "beat_confidence": 0.0}
        row = connection.execute(
            "SELECT beat_confidence FROM beat_timestamps WHERE track_id = ? LIMIT 1",
            (track_id,),
        ).fetchone()
        confidence = float(row["beat_confidence"]) if row else 0.0
    return {"beats": beats, "beat_confidence": confidence}


def _analyze_beats_for_track(database_path: Path, track_id: int) -> dict:
    """Detect beats for one track's file and phrase-fill its cue pads.

    Read-only toward the audio file. On detection failure, existing beats and
    pads are preserved (no overwrite) and a 400-worthy error is raised.
    """
    with database.connect(database_path) as connection:
        track = database.get_track_by_id(connection, track_id)
        if track is None:
            raise KeyError(f"Track not found: {track_id}")
        file_path = track["file_path"]

    result = detect_beat_timestamps(file_path)
    if not result.beat_timestamps:
        raise ValueError(
            "Beat detection found no beats for this track. "
            "Existing beats and pads were preserved."
        )

    with database.connect(database_path) as connection:
        stored_beats = database.replace_beat_timestamps(
            connection,
            track_id=track_id,
            file_path=file_path,
            beat_timestamps=result.beat_timestamps,
            beat_confidence=result.beat_confidence,
        )
        connection.commit()

    pads = pad_service.autofill_pads(track_id, database_path=database_path)
    return {"pads": pads, "stored_beats": stored_beats}


def _browse_for_folder() -> str | None:
    script = (
        "import tkinter, tkinter.filedialog;"
        "root = tkinter.Tk();"
        "root.withdraw();"
        "root.lift();"
        "root.attributes('-topmost', True);"
        "path = tkinter.filedialog.askdirectory(title='Select music folder');"
        "root.destroy();"
        "print(path, end='')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        folder = result.stdout.strip()
        return folder if folder else None
    except Exception:
        return None
