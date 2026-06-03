# DJ CueCraft

DJ CueCraft is a local-first DJ library preparation tool. The Phase 1 MVP scans a local music folder, reads basic embedded metadata, stores track records in SQLite, and proposes DJ-friendly genre and decade normalization for review.

This is not a DJ performance app. It does not play tracks, edit Engine DJ or Rekordbox databases, write cue points, rewrite audio files, sync to the cloud, or use external metadata APIs.

## MVP Scope

- Scan local folders for `.mp3`, `.flac`, `.m4a`, and `.wav` files.
- Read basic metadata with Mutagen.
- Store scanned track records in a local SQLite database.
- Propose rule-based genre and decade normalization.
- Export scanned tracks and proposed normalized tags to CSV.
- Experimentally detect BPM and store results in SQLite.
- Experimentally detect beat positions and propose cue points in SQLite.
- Mark broad or uncertain tags as `needs_review`.
- Keep all metadata changes as proposals only.

## Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

For experimental BPM detection, install the optional audio dependencies:

```powershell
python -m pip install -e ".[audio,dev]"
```

## Example Scan

```powershell
python -m dj_library_prep.cli scan "C:\Path\To\Music" --database djcuecraft.sqlite3
```

The scan reads files and records proposed metadata cleanup in SQLite. It does not write anything back to audio files.

## Example CSV Export

```powershell
python -m dj_library_prep.cli export-csv --output exports/scan_results.csv
```

The export reads scanned records from `djcuecraft.sqlite3` and writes a CSV review file. It includes original metadata, proposed normalized metadata, confidence scores, `review_status`, and missing field warnings. It does not write anything back to audio files.

## Example Correction Import

Edit the exported CSV's normalized genre fields, save it as a corrected copy, then import it:

```powershell
python -m dj_library_prep.cli import-corrections exports/scan_results_corrected.csv
```

The import updates changed `normalized_primary_genre`, `normalized_subgenre`, and `dj_use_tags` fields in SQLite, marks corrected tracks as `approved`, and records each correction in `correction_history`. It does not write anything back to audio files.

## Example BPM Analysis

```powershell
python -m dj_library_prep.cli analyze-bpm "samples/test_music"
```

BPM analysis uses local audio analysis and stores `bpm` and `bpm_confidence` in SQLite only. Low-confidence BPM values are marked `needs_review`. It does not write anything back to audio files.

## Example Beat And Cue Analysis

```powershell
python -m dj_library_prep.cli analyze-beats "samples/test_music"
python -m dj_library_prep.cli export-cues-csv --output exports/cue_points.csv
```

Beat analysis stores beat timestamps separately from track metadata and proposes cue points for Intro, 8 Beats In, 16 Beats In, 32 Beats In, and 64 Beats In. Cue points include `cue_confidence` and `review_status`. Nothing is written to audio files or DJ software libraries.

## Tests

```powershell
cd backend
python -m pytest
```
