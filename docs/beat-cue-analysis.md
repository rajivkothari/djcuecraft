# Beat And Cue Analysis

Beat and cue analysis is experimental and local-first.

## Commands

```powershell
python -m dj_library_prep.cli analyze-beats "samples/test_music"
python -m dj_library_prep.cli export-cues-csv --output exports/cue_points.csv
```

Use a different auto-cue preset:

```powershell
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue-preset performance
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue-preset phrase
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue-preset extended
python -m dj_library_prep.cli analyze-beats "samples/test_music" --cue-preset minimix
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

## Presets

### `performance` (default)

8 cues: beat-indexed intro/body anchors plus time-fraction tail anchors.

Beat-indexed (forward from track start):

- Intro — beat 0
- 8 Beats In — beat 8
- 32 Beats In — beat 32
- 64 Beats In — beat 64
- 128 Beats In — beat 128

Time-fraction (relative to full track duration):

- Breakdown — 40% through
- Build — 70% through
- Outro — 88% through

Time-fraction cues snap to the nearest detected beat. They require the full track duration to be readable — if duration cannot be determined they are silently skipped.

### `minimix`

8 cues designed for quick in/out mixing. One beat-indexed start cue plus seven time-fraction cues evenly distributed across the track.

- Intro — beat 0
- 1/4 — 25%
- Mid — 50%
- 3/4 — 75%
- Outro Prep — 85%
- Outro — 90%
- Exit — 95%
- End — 99%

### `starter`

5 cues covering the first 64 beats:

- Intro, 8 Beats In, 16 Beats In, 32 Beats In, 64 Beats In

### `phrase`

5 cues at 32-beat phrase intervals: Intro, Phrase 1, Phrase 2, Phrase 3, Phrase 4.

### `extended`

7 cues covering the first 128 beats: Intro, 8 Beats In, 16 Beats In, 32 Beats In, 64 Beats In, 96 Beats In, 128 Beats In.

## Cue anchor types

**Beat-index anchors** (`beat_index` field): placed at a fixed number of detected beats from the start of the track. Cues whose beat index exceeds the detected beat count are silently skipped.

**Time-fraction anchors** (`time_fraction` field): placed at a fraction of the full track duration (0.0 = start, 1.0 = end), then snapped to the nearest detected beat. These require that the file's full duration is readable via librosa. If duration is unavailable (e.g. truncated metadata, analysis failure), the cue is silently skipped. Full track duration is captured with `librosa.get_duration(path=path)` before the 180-second truncated audio load.

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
