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
- 16 Beats In — beat 16
- 32 Beats In — beat 32
- 64 Beats In — beat 64

Time-fraction (relative to full track duration):

- Mid — 55% through
- Last Chorus — 75% through
- Outro — 90% through

Time-fraction cues snap to the nearest detected beat. They are silently skipped if the full track duration is unavailable or if no beat falls within 2.0 seconds of the target position.

### `minimix`

8 cues designed as manual-anchor orientation points for quick-mix sets. All positions are auto-placed as starting anchors — the DJ renames and repositions them from the playhead. One beat-indexed start cue plus seven equally-spaced time-fraction cues.

- Track 1 — beat 0
- Track 2 — 14% through
- Track 3 — 28% through
- Track 4 — 42% through
- Track 5 — 56% through
- Track 6 — 70% through
- Track 7 — 84% through
- Track 8 — 95% through

### `starter`

5 cues covering the first 64 beats:

- Intro, 8 Beats In, 16 Beats In, 32 Beats In, 64 Beats In

### `phrase`

5 cues at 32-beat phrase intervals: Intro, Phrase 1, Phrase 2, Phrase 3, Phrase 4.

### `extended`

7 cues covering the first 128 beats: Intro, 8 Beats In, 16 Beats In, 32 Beats In, 64 Beats In, 96 Beats In, 128 Beats In.

## Cue anchor types

**Beat-index anchors** (`beat_index` field): placed at a fixed number of detected beats from the start of the track. Cues whose beat index exceeds the detected beat count are silently skipped.

**Time-fraction anchors** (`time_fraction` field): placed at a fraction of the full track duration (0.0 = start, 1.0 = end), then snapped to the nearest detected beat. These require that the file's full duration is readable via librosa. If duration is unavailable (e.g. truncated metadata, analysis failure), the cue is silently skipped. If no detected beat falls within 2.0 seconds of the target position, the cue is also skipped. Duplicate resolutions (two time-fraction cues resolving to the same beat index) keep only the first and skip the second. Full track duration is captured with `librosa.get_duration(path=path)`. The full track audio is loaded for beat detection (no truncation) so that beat timestamps cover the entire duration, which is required for time-fraction cue placement. Longer tracks take proportionally longer to analyze. BPM detection uses a 120-second sample (sufficient for tempo estimation).

Custom `--cue` CLI entries use `LABEL=BEAT_INDEX` format and are always beat-index anchors. Time-fraction anchors are available only through built-in presets.

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
