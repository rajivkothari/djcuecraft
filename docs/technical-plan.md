# Technical Plan

## Architecture

The Phase 1 backend is a small Python package:

- `scanner.py` finds supported audio files.
- `metadata.py` reads embedded tags with Mutagen.
- `genre_normalizer.py` proposes genre and decade normalization.
- `models.py` defines track records and review status values.
- `database.py` owns SQLite schema creation and inserts.
- `bpm_analyzer.py` performs experimental local BPM analysis.
- `beat_analyzer.py` performs experimental beat timestamp analysis and cue point proposal.
- `cue_exporter.py` exports proposed cue points for review.
- `review_service.py` owns review-table read/update behavior.
- `local_api.py` serves a local JSON API and static review UI.
- `cli.py` provides the first operational workflow.

## Backend Modules

The CLI calls the scanner, extracts metadata for each file, normalizes fields, then saves track records to SQLite. The CSV export command reads those records from SQLite and writes a reviewable CSV file. The correction import command reads a manually edited CSV and applies corrected normalized genre fields back to SQLite only. The BPM command analyzes local audio and stores BPM proposals in SQLite only. The beat command stores beat timestamps separately and creates proposed cue points in SQLite only. The local review UI reads and updates review fields through a small JSON API. All metadata cleanup outputs are proposals until explicitly reviewed.

## Local Database Plan

SQLite is the persistence layer for scanned track records. Phase 1 uses a `tracks` table with enough columns to support review queues and future update workflows, including experimental `bpm` and `bpm_confidence` fields. Beat timestamps live in `beat_timestamps`, and proposed cue points live in `cue_points`. It includes the legacy `correction_history` table for CSV correction details and the general `review_history` table for audit records from UI edits and CSV correction imports.

Schema initialization uses SQLite `PRAGMA user_version` to track the current schema version. Forward migrations live in `database.py`, so legacy local databases can be upgraded without replacing user review data.

CSV export is read-only with respect to music files. It exports database records for review and does not apply metadata changes to audio files.

Correction import is also read-only with respect to music files. It updates only SQLite rows, marks changed tracks as `approved`, and records original suggested genre, corrected genre, timestamp, and source CSV file.

Review history is recorded locally in SQLite. Each meaningful UI edit or CSV correction import stores previous and new normalized metadata, previous and new review status, genre confidence values, timestamp, track id, file path, and source. No history row is created for no-op saves.

BPM analysis is also read-only with respect to music files. It updates only SQLite `bpm`, `bpm_confidence`, `review_status`, and `updated_at` values.

Beat and cue analysis is also read-only with respect to music files and DJ software. It updates only SQLite beat timestamp and cue point tables.

The review UI is read-only with respect to music files. It updates only SQLite normalized metadata and review status fields.

## Frontend Plan

The minimal UI lives in `frontend/` as static HTML, CSS, and JavaScript. It talks to `local_api.py` over local HTTP. This keeps frontend logic separate from backend scanning, normalization, storage, and review update logic, and leaves room for a later Tauri or Electron shell.

## BPM Analysis Limitations

BPM detection is experimental. It uses `librosa` to estimate tempo from local audio onset patterns. Results may be unreliable for tracks with variable tempo, long intros, sparse percussion, live recordings, tempo changes, half-time/double-time ambiguity, or low-quality files. Low-confidence values are marked `needs_review` and should be treated as proposals.

## Beat And Cue Limitations

Beat timestamp analysis is experimental. Cue points are generated from detected beat positions and may be wrong when beat detection drifts, starts late, doubles or halves tempo, or misses a downbeat. Proposed cue points should be reviewed before use in any DJ workflow.

## Future Frontend Plan

The repository is structured so a desktop frontend can be added later under a separate app directory, using Tauri/React or Electron/React. The backend should remain callable from scripts or a service boundary.

## Future Beat Detection And Cue Point Plan

Beat-grid writing and DJ software cue-point writing are intentionally out of scope for Phase 1. Future work should improve analysis modules while keeping outputs as proposals, not automatic edits.
