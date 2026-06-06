# DJ CueCraft

DJ CueCraft is a local-first DJ library preparation tool. The Phase 1 MVP scans a local music folder, reads basic embedded metadata, stores track records in SQLite, and proposes DJ-friendly genre and decade normalization for review.

This is not a DJ performance app. It does not play tracks, edit Engine DJ or Rekordbox databases, write cue points, rewrite audio files, sync to the cloud, or use external metadata APIs.

## Safety First

**Always work on a copy of your music library, not the originals.**

- DJ CueCraft never modifies your audio files in this version. All changes are proposals stored in a local SQLite database.
- BPM detection and beat/cue analysis are experimental. Results are often inaccurate for Indian, Latin, live, and variable-BPM tracks. Treat every BPM and cue proposal as a draft until you review it.
- Exports are sidecar review files only. They do not write back to audio files, ID3 tags, Engine DJ, Rekordbox, or any other DJ software.
- If you are testing for the first time: copy a small folder of tracks to a safe location and run the scan there first.

## MVP Scope

- Scan local folders for `.mp3`, `.flac`, `.m4a`, and `.wav` files.
- Read basic metadata with Mutagen.
- Store scanned track records in a local SQLite database.
- Propose rule-based genre and decade normalization.
- Export scanned tracks and proposed normalized tags to CSV.
- Experimentally detect BPM and store results in SQLite.
- Experimentally detect beat positions and propose cue points in SQLite.
- Review scanned tracks in a minimal local desktop-friendly UI.
- Mark broad or uncertain tags as `needs_review`.
- Keep all metadata changes as proposals only.

## Setup

**Windows (PowerShell)**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

**Mac / Linux**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Setup also installs the `dj-library-prep` console command. The examples below use `python -m dj_library_prep.cli` so the active Python environment is explicit.

For experimental BPM detection, install the optional audio dependencies:

```bash
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

Beat analysis stores beat timestamps separately from track metadata and proposes cue points. The default `performance` preset places beat-indexed cues at Intro, 8 Beats In, 32 Beats In, 64 Beats In, and 128 Beats In, plus time-fraction tail cues at Breakdown (40%), Build (70%), and Outro (88%) of the track's full duration. Cue points include `cue_confidence` and `review_status`. Nothing is written to audio files or DJ software libraries.

Auto-cue setup can use a preset or custom cue template:

```powershell
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue-preset performance
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue-preset minimix
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue-preset phrase
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue "Load=0" --cue "Drop Prep=32"
```

Auto-cue analysis fills in missing cue labels only. Existing cue points with matching labels are preserved and are not overwritten.

After beats are stored, fill pads for all library tracks at once:

```powershell
python -m dj_library_prep.cli auto-fill-pads --database djcuecraft.sqlite3
python -m dj_library_prep.cli auto-fill-pads --phrase-length 32 --force
```

`--force` re-fills tracks that already have pads (manual pads are still preserved).

## Example Review UI

Double-click `launch-ui.bat`, or run:

```powershell
python -m dj_library_prep.cli serve-ui --database djcuecraft.sqlite3
```

Open `http://127.0.0.1:8765` in a browser. The UI shows scanned tracks, original metadata, proposed normalized metadata, confidence scores, and review status controls. Edits are saved to SQLite only. It does not write anything back to audio files.

The UI also includes Auto Cues controls for running beat analysis from the browser and reviewing stored cue proposals.

Manual UI edits and CSV correction imports are recorded in the local `review_history` audit table. UI edits use `source = review_ui`; CSV imports use `source = csv_import`.

## Tests

```powershell
cd backend
python -m pytest
```
