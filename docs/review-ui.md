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
- Stored cue point proposals

## What It Can Edit

- `normalized_decade`
- `normalized_primary_genre`
- `normalized_subgenre`
- `dj_use_tags`
- `review_status`

## Auto Cue Setup

The UI can run beat analysis for a local music folder and store cue proposals in SQLite. Choose a preset or enter custom cue rows with `LABEL=BEAT_INDEX`.

Auto-cue analysis inserts missing cue labels only. Existing cue points with matching labels are preserved.

## Bulk Selection

Each track row has a checkbox in the first column. Check multiple tracks to apply a status change to all of them at once.

- The checkbox in the table header selects/deselects all currently visible rows.
- The bulk action bar appears above the track table when one or more tracks are selected.
- Three actions are available: **Approve Selected**, **Reject Selected**, **Skip Selected**.
- Bulk actions only change `review_status` — they never modify normalized genre, decade, subgenre, or tag fields. Those require individual per-track review.
- Tracks already at the target status are silently skipped (no history record created for those).
- Non-existent track IDs are silently skipped.

Bulk actions create a row in `review_history` for each track that actually changes:

| Field | Value |
|---|---|
| `source` | `bulk_action` |
| `action` | `bulk_approve` / `bulk_reject` / `bulk_skip` |
| `reason` | `"Bulk {status} applied to N tracks."` |

## Safety

The UI writes review edits to SQLite only. It does not write metadata, cue points, or any other changes back to audio files or DJ software.

Meaningful UI edits create a row in `review_history` with `source = review_ui`. No-op saves do not create history rows.

## Architecture

The frontend is static HTML, CSS, and JavaScript under `frontend/`. The backend review logic lives in `review_service.py`, and `local_api.py` exposes a small local JSON API. This keeps the frontend ready for a future Tauri or Electron wrapper without moving database logic into browser code.

The UI can fetch a track's history from `GET /api/tracks/{track_id}/history`.

### API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/tracks` | List tracks (optional `?status=` filter) |
| `PATCH` | `/api/tracks/{id}` | Update one track's review fields |
| `POST` | `/api/tracks/bulk-update` | Bulk status update for multiple tracks |
| `GET` | `/api/tracks/{id}/history` | Review history for one track |
