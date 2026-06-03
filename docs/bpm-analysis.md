# BPM Analysis

BPM analysis is experimental and local-first.

## Command

```powershell
python -m dj_library_prep.cli analyze-bpm "samples/test_music"
```

Install optional audio dependencies first:

```powershell
python -m pip install -e ".[audio,dev]"
```

## Storage

Detected BPM values are stored in SQLite only:

- `bpm`
- `bpm_confidence`

Low-confidence BPM values are marked `needs_review`.

The command does not write BPM values to audio files.

## Known Limitations

The current implementation uses `librosa` tempo estimation. BPM estimates can be wrong for:

- variable-tempo tracks
- long intros or outros
- sparse percussion
- live recordings
- half-time or double-time ambiguity
- tracks with tempo changes
- corrupted or unsupported files

Treat BPM results as reviewable proposals, not final metadata.
