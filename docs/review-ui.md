# Review UI

The review UI is a minimal local interface for scanned track review.

## Command

```powershell
python -m dj_library_prep.cli serve-ui --database djcuecraft.sqlite3
```

Open `http://127.0.0.1:8765`.

## What It Shows

- Track table
- Original metadata
- Proposed normalized metadata
- Confidence scores
- Review status
- Missing metadata warnings

## What It Can Edit

- `normalized_decade`
- `normalized_primary_genre`
- `normalized_subgenre`
- `dj_use_tags`
- `review_status`

## Safety

The UI writes review edits to SQLite only. It does not write metadata, cue points, or any other changes back to audio files or DJ software.

Meaningful UI edits create a row in `review_history` with `source = review_ui`. No-op saves do not create history rows.

## Architecture

The frontend is static HTML, CSS, and JavaScript under `frontend/`. The backend review logic lives in `review_service.py`, and `local_api.py` exposes a small local JSON API. This keeps the frontend ready for a future Tauri or Electron wrapper without moving database logic into browser code.

The UI can fetch a track's history from `GET /api/tracks/{track_id}/history`.
