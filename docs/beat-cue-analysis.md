# Beat And Cue Analysis

Beat and cue analysis is experimental and local-first.

## Commands

```powershell
python -m dj_library_prep.cli analyze-beats "samples/test_music"
python -m dj_library_prep.cli export-cues-csv --output exports/cue_points.csv
```

Install optional audio dependencies first:

```powershell
python -m pip install -e ".[audio,dev]"
```

## Storage

Beat timestamps are stored separately from track metadata in `beat_timestamps`.

Proposed cue points are stored in `cue_points` with:

- `cue_label`
- `beat_index`
- `timestamp_seconds`
- `cue_confidence`
- `review_status`

The current proposal set is:

- Intro
- 8 Beats In
- 16 Beats In
- 32 Beats In
- 64 Beats In

## Safety

The command does not write cue points to audio files, Engine DJ, Rekordbox, MIXO, or any other DJ software.

## Known Limitations

Cue proposals depend on beat detection quality. Results may be wrong for:

- tracks with silence or long intros
- variable tempo
- live recordings
- half-time or double-time ambiguity
- beat grids that drift
- songs where the first detected beat is not the musical downbeat
- corrupted or unsupported files

Treat cue points as proposals for review, not final DJ-library data.
