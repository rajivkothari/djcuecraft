# Beat And Cue Analysis

Beat and cue analysis is experimental and local-first.

## Commands

```powershell
python -m dj_library_prep.cli analyze-beats "samples/test_music"
python -m dj_library_prep.cli export-cues-csv --output exports/cue_points.csv
```

Use a different auto-cue preset:

```powershell
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue-preset phrase
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue-preset extended
```

Or define a custom cue template. Each `--cue` value uses `LABEL=BEAT_INDEX`, and repeated `--cue` values replace the preset:

```powershell
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue "Load=0" --cue "Drop Prep=32" --cue "Phrase 2=64"
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

The default `starter` proposal set is:

- Intro
- 8 Beats In
- 16 Beats In
- 32 Beats In
- 64 Beats In

Additional presets:

- `phrase`: Intro, Phrase 1, Phrase 2, Phrase 3, Phrase 4 at 32-beat phrase intervals.
- `extended`: the starter cues plus 96 Beats In and 128 Beats In.

Custom templates are stored with the provided cue labels and beat indexes. Cue points whose beat indexes exceed the detected beat count are skipped.

Auto-cue analysis is additive for cue points: it inserts missing cue labels only. If a track already has a cue point with the same label, that existing cue's beat index, timestamp, confidence, and review status are preserved.

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
