# DJ Cue Craft Product Memory

Last updated: 2026-06-05

## Product Intent

DJ Cue Craft is a local-first, review-first DJ library preparation utility. Its job is to scan a music library, read existing metadata, suggest safer normalized metadata, propose cue points later, and export approved changes without directly modifying the user's music files or DJ software libraries.

The product posture is conservative: every automated result is a proposal until the DJ reviews it.

## Non-Negotiable Safety Rules

- Do not overwrite audio files.
- Do not write ID3 tags in the MVP.
- Do not directly write Engine DJ, MIXO, Rekordbox, Serato, Traktor, or other DJ software databases yet.
- Do not overwrite existing cue points.
- Cue point generation must fill missing cue labels only.
- Export only approved or edited metadata by default.
- Low-confidence metadata must remain reviewable.
- Keep changes local and reversible.

## Current Architecture

- Backend: Python package under `backend/src/dj_library_prep`.
- Persistence: local SQLite database.
- UI: static HTML, CSS, and JavaScript in `frontend`, served by the local Python API.
- Tests: pytest suite under `backend/tests`.
- Main local database tables:
  - `tracks`
  - `review_history`
  - `correction_history`
  - `beat_timestamps`
  - `cue_points`

## Implemented Features

- Safe folder scanning for supported audio files.
- Basic metadata extraction into SQLite.
- Failure-tolerant scanning: a bad file should not crash the whole scan.
- Duplicate handling by unique `file_path`.
- Existing reviewed decisions are preserved during rescan.
- Metadata suggestion engine for decade, genre, subgenre, normalized label, confidence, and review flag.
- Genre taxonomy includes general, Latin, Indian, Bollywood, Punjabi, Tamil, and DJ utility patterns.
- Review UI for scanned tracks.
- Review statuses:
  - `pending`
  - `needs_review`
  - `approved`
  - `edited`
  - `rejected`
  - `skipped`
- Review actions in the UI:
  - approve
  - save edit
  - reject
  - skip
  - view history
- Audit logging for meaningful review changes.
- Audit entries capture track, file path, action, previous and new review status, previous and new normalized values, confidence, source, timestamp, and reason.
- CSV correction import still updates SQLite only.
- Experimental BPM analysis stores BPM proposals in SQLite only.
- Experimental beat analysis stores beat timestamps and cue point proposals in SQLite only.
- Auto cue logic inserts missing cue labels only and preserves existing cue labels.
- Safe MVP metadata export:
  - CSV export for approved and edited tracks only.
  - JSON sidecar export for approved and edited tracks only.
  - Exports include original metadata, approved normalized metadata, confidence, review status, and latest audit reference when available.

## Current Commands

Common backend commands:

```powershell
python -m dj_library_prep.cli scan "C:\Path\To\Music" --database djcuecraft.sqlite3
python -m dj_library_prep.cli serve-ui --database djcuecraft.sqlite3
python -m dj_library_prep.cli export-csv --database djcuecraft.sqlite3 --output approved.csv
python -m dj_library_prep.cli export-json --database djcuecraft.sqlite3 --output approved.json
python -m dj_library_prep.cli analyze-beats "C:\Path\To\Music" --database djcuecraft.sqlite3 --cue-preset starter
python -m dj_library_prep.cli export-cues-csv --database djcuecraft.sqlite3 --output cue_points.csv
```

## Current Export Behavior

- `export-csv` now means safe approved metadata export.
- `export-json` writes a structured sidecar file.
- Default metadata export includes only:
  - `approved`
  - `edited`
- Default metadata export excludes:
  - `pending`
  - `needs_review`
  - `rejected`
  - `skipped`
- Export does not write audio files, ID3 tags, or DJ software databases.
- Export refuses the wrong file extension for CSV or JSON outputs.

## Auto Cue Status

Auto cues are still experimental. The current system can analyze beats and create proposed cue points in SQLite. It does not write cues to audio files or DJ software.

Important behavior:

- Missing cue labels are inserted.
- Existing cue labels are preserved.
- Cue proposals include confidence and review status.
- Cue export is currently CSV-only and should be treated as a review/report export, not a direct DJ software import.

## Known Gaps

- Immutable AI suggestion snapshots are not fully separated from final reviewed metadata.
- Export preparation itself is not yet written as an audit event.
- Bulk approval is not implemented yet.
- Review-required filtering exists mainly through status and UI flags, but needs a stronger dedicated workflow.
- Engine DJ and MIXO compatibility are not proven and should remain future adapter work.
- The UI is local and functional, but not yet a polished non-technical desktop app.
- Cue point review workflow is not yet as mature as metadata review.
- BPM and beat analysis are experimental and can be wrong.

## Near-Term Priorities

1. Separate immutable AI suggestions from final approved or edited metadata.
2. Add `export_prepared` audit logging with export path, count, statuses, and timestamp.
3. Improve low-confidence review filtering in the UI.
4. Build a safer cue review workflow before any cue export adapter work.
5. Keep Engine DJ and MIXO as export adapters only after their formats are verified.

## Current QA Position

The metadata MVP is safe enough to use on a copied test library as a scan, review, and sidecar export workflow.

It is not yet safe to use for direct DJ software database writing, ID3 tag writing, or automatic cue writing.
