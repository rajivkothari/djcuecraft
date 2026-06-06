# Codex Handoff — DJ CueCraft

Last updated: 2026-06-06
Branch: `claude/sleepy-volta-AlMso`
All 131 tests pass.

---

## What Was Done in This Session

### Context

An external audit was run against the full codebase and a prioritized implementation backlog was produced (see below for the backlog tiers). Claude then implemented all **P0 items** — the four changes required before copied-library testing. Nothing else was modified.

---

## P0 Changes Committed in This Session

### P0-1 — BPM Re-Run Now Skips Approved and Edited Tracks

**Files changed:** `bpm_analyzer.py`, `cli.py`
**Tests added:** `test_bpm_analyzer.py` (4 new tests)

**What changed:**

`analyze_bpm_for_folder()` in `bpm_analyzer.py` now accepts a `force: bool = False` keyword argument. Before running `detect_bpm()` on any track, it checks the track's existing `review_status`. If the status is `approved` or `edited`, the track is skipped and counted in a new `skipped_reviewed_tracks` field on `BpmAnalysisSummary`.

The CLI `analyze-bpm` command gained a `--force` flag that passes `force=True` to bypass the protection. The summary output prints a line like `skipped (already reviewed): 3 — use --force to re-analyze` when any tracks are skipped.

**Why:** Re-running `analyze-bpm` previously overwrote BPM values for tracks a DJ had already manually verified. This silently undid reviewed work — the same class of bug that the genre/decade rescan protection already correctly handles.

**The constant** `REVIEWED_STATUSES = frozenset({"approved", "edited"})` is defined in `bpm_analyzer.py`. If the set of protected statuses ever needs to change (e.g., to also protect `rejected` tracks), update that constant.

---

### P0-2 — Export Commands Now Refuse to Overwrite Existing Files

**Files changed:** `cli.py`
**Tests added:** `test_cli.py` (3 new tests)

**What changed:**

Both `export-csv` and `export-json` CLI commands now check whether the output file already exists before calling the exporter. If it does and `--overwrite` was not passed, they print an error message and return exit code 1. The actual exporter functions in `csv_exporter.py` are unchanged — the guard is in `cli.py` only, in a small helper `_output_exists_and_no_overwrite(output, overwrite)`.

```
Error: output file already exists: exports/approved.csv
Use --overwrite to replace it.
```

**Why:** Silent overwrite of a previous export could destroy a shared reference file without any warning. The `--overwrite` flag makes intent explicit.

**Note for future work:** This guard is in the CLI layer only. If `export_tracks_to_csv` or `export_approved_tracks_to_json` are called directly from Python code (not CLI), they still silently overwrite. If a future API endpoint or other caller needs the same protection, move the check into the exporter functions themselves.

---

### P0-3 — README Safety Callout and Mac/Linux Setup

**Files changed:** `README.md`

**What changed:**

Added a "Safety First" section immediately after the project description, before Setup. It contains four bullet points: always work on a copy, the tool never modifies audio files, BPM/cue proposals are experimental, and a first-run recommendation to test on a small copied folder.

Added Mac/Linux `bash` setup instructions alongside the existing PowerShell instructions under the Setup section. The `pip install` examples now use plain `bash` code fences rather than `powershell`.

---

### P0-4 — Database Indexes for track_id Columns

**Files changed:** `database.py`
**Tests added:** `test_database.py` (2 new tests)

**What changed:**

`CURRENT_SCHEMA_VERSION` bumped from `2` to `3`. A new migration function `_migrate_track_lookup_indexes()` was added and registered as migration `3` in the `MIGRATIONS` tuple. It creates four indexes if they do not already exist:

| Index | Table | Column |
|---|---|---|
| `idx_beat_timestamps_track_id` | `beat_timestamps` | `track_id` |
| `idx_cue_points_track_id` | `cue_points` | `track_id` |
| `idx_review_history_track_id` | `review_history` | `track_id` |
| `idx_correction_history_track_id` | `correction_history` | `track_id` |

The migration uses `CREATE INDEX IF NOT EXISTS` so it is idempotent. Existing databases will have the indexes added on next `connect()` call. No data is changed.

The existing migration for version 2 (`_migrate_review_history_audit_columns`) was previously registered as `(CURRENT_SCHEMA_VERSION, ...)` which was a fragile pattern — it used the constant rather than a literal version number. This has been corrected: it is now registered as `(2, _migrate_review_history_audit_columns)`. This is a correctness fix; the behavior for new databases is unchanged.

A helper `_create_version_2_database()` was added to `test_database.py` to support the migration regression test.

---

---

## Cue Point Rename (Added After P0)

**Files changed:** `database.py`, `local_api.py`, `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
**Tests added:** `test_local_api.py` (2 new tests)

**What changed:**

The cue table in the review UI now has an Actions column with a pencil (✎) edit button on every row. Clicking it turns the Cue label cell into an inline text input with Save and Cancel buttons. Enter and Escape are keyboard shortcuts. On save, a `PATCH /api/cue-points/{id}` request is sent with `{"cue_label": "new name"}`. The label updates in place on success without reloading the table.

**Backend:**
- `database.update_cue_label(connection, cue_id, new_label)` — updates `cue_label` and `updated_at`, returns the updated row
- `database.get_cue_point_by_id(connection, cue_id)` — used internally by update and also available for other callers
- `PATCH /api/cue-points/{id}` in `local_api.py` — validates non-empty label, calls update, returns `{"cue_point": {...}}`. Returns 400 for empty/whitespace labels, 404 for unknown IDs.

**Note:** This endpoint only renames the label. It does not change `review_status`, `beat_index`, or `timestamp_seconds`. The cue review workflow (P2-3) will layer on top of this when built — it will need its own `PATCH /api/cue-points/{id}` fields for `review_status`.

---

## Cue Editor: Waveform + Play + Metronome + 8 Pads (Added After Cue Rename)

**Files changed:** `database.py`, `pads.py` (new), `local_api.py`, `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
**Tests added:** `test_pads.py` (new, 11 tests), `test_local_api.py` (4 new), `test_database.py` (2 new)

A persistent bottom panel cue editor. Click any track's name cell to load it into the editor.

**Audio playback & waveform (client-side, no new backend audio deps):**
- `GET /api/audio?path=...` serves the local audio file **read-only** (validates extension + existence, sets content-type). It never modifies the file.
- The browser fetches the file once, decodes it with the Web Audio API (`decodeAudioData`), and uses the same `AudioBuffer` for both the waveform drawing and playback (`AudioBufferSourceNode`). No HTTP range/seeking complexity, and `librosa` is NOT required for the waveform.
- Playhead, click-to-seek, play/pause/stop are all driven from `audioContext.currentTime`.

**Metronome:** Web Audio oscillator clicks scheduled at the track's stored `bpm` (from `tracks.bpm`), phase-anchored to the first pad position. Toggle in the transport bar. Only ticks while playing. If the track has no BPM, it stays silent.

**8 pads per track (new `pads` table, schema v4):**
- `pads` columns: `id, track_id, pad_index (0-7), label, timestamp_seconds, beat_index, source ('auto'|'manual'), created_at, updated_at`, `UNIQUE(track_id, pad_index)`. Index `idx_pads_track_id`.
- Logic lives in `pads.py` (service layer, not in `database.py`): `list_pads_for_track`, `set_pad`, `clear_pad`, `autofill_pads`.
- **Auto-fill** (`POST /api/tracks/{id}/pads/auto-fill`) places phrase pads at beats 0, 32, 64, … read from the track's stored `beat_timestamps`. Requires that beats were already detected (run folder Analyze first); returns 400 with a clear message if not. Phrase length defaults to 32 beats, overridable via `{"phrase_length": N}`.
- **Rename + re-capture** (`PUT /api/tracks/{id}/pads/{idx}`): `{"label": "..."}` renames, `{"timestamp_seconds": N}` re-captures position to the current playhead. Either action marks the pad `source='manual'`. Renaming preserves the captured position and vice versa.
- **Preserve invariant:** `autofill_pads` never overwrites a `source='manual'` pad. This mirrors the project-wide "don't clobber reviewed work" rule.
- `GET /api/tracks/{id}/pads` always returns 8 slots (empty slots filled with blank placeholders so the UI grid is stable).
- `DELETE /api/tracks/{id}/pads/{idx}` clears a slot.

**New HTTP verbs:** `local_api.py` now implements `do_PUT` and `do_DELETE` in addition to GET/POST/PATCH.

**Frontend structure:** `#cueEditor` is `position: fixed` at the bottom (`main` has `padding-bottom` to compensate). Pads render from a `<template id="padTemplate">`. The waveform is a `<canvas>` redrawn each animation frame while playing.

**Notes / future hooks for Codex:**
- Pads and the existing `cue_points` table are **separate systems**. `cue_points` is the flat per-folder auto-cue list (and the rename feature); `pads` is the per-track 8-slot editor. They can be unified later, but were kept separate to avoid the `cue_points` `UNIQUE(track_id, cue_label)` constraint blocking two pads with the same name.
- The metronome anchor is the first pad with a timestamp; if you later store a true downbeat offset, use it here.
- `decodeAudioData` covers mp3/wav/m4a everywhere and FLAC in modern Chromium/Firefox. If a user reports a FLAC that won't load, that's a browser codec gap, not a backend bug.
- The pads were lost-feature parity work — when Codex's original waveform/pad code was overwritten in the merge, this is the committed replacement.

---

---

## `performance` and `minimix` Cue Presets + Time-Fraction Anchors

**Files changed:** `beat_analyzer.py`, `tests/test_beat_analyzer.py`, `README.md`, `docs/beat-cue-analysis.md`
**Tests added:** 14 new tests in `test_beat_analyzer.py` (125 total)

### What changed

**`CueTemplate` extended:** added `beat_index: int | None = None` (was required `int`) and `time_fraction: float | None = None`. Backward compatible — all existing `CueTemplate("label", N)` calls still work since `beat_index` is positional. Every cue must have at least one anchor type set; `_normalized_cue_template` validates both fields.

**`BeatAnalysisResult` extended:** added `total_duration_seconds: float = 0.0`. Default `0.0` preserves backward compatibility for monkeypatched tests that don't pass this field.

**`detect_beat_timestamps` updated:** calls `librosa.get_duration(path=path)` before the truncated 180-second audio load to capture the full file duration. Stored in `BeatAnalysisResult.total_duration_seconds`.

**`propose_cue_points` updated:** accepts `total_duration_seconds: float | None = None`. For time-fraction cues, resolves `time_fraction * total_duration_seconds` to the nearest beat via `_nearest_beat_index()`. If `total_duration_seconds` is not provided or is `0.0`, time-fraction cues are silently skipped (not an error).

**`_nearest_beat_index()` added:** pure-Python helper — `min(range(len(beats)), key=lambda i: abs(beats[i] - target))`.

**Two new presets:**

| Preset | Beat-indexed cues | Time-fraction cues |
|--------|------------------|-------------------|
| `performance` | Intro(0), 8 Beats In(8), 16 Beats In(16), 32 Beats In(32), 64 Beats In(64) | Mid(0.55), Last Chorus(0.75), Outro(0.90) |
| `minimix` | Track 1(0) | Track 2(0.14), Track 3(0.28), Track 4(0.42), Track 5(0.56), Track 6(0.70), Track 7(0.84), Track 8(0.95) |

**`DEFAULT_CUE_PRESET` changed** from `"starter"` to `"performance"`.

**Existing tests updated:** three tests that relied on the `"starter"` default were updated to pass `cue_template=cue_template_for_preset("starter")` explicitly. All previous behavior is preserved.

### Design notes for Codex

- Time-fraction cues and beat-indexed cues can coexist in one preset. The performance preset deliberately places beat-indexed cues at the beginning (where exact beat counts matter for DJ cueing) and time-fraction cues toward the end (where position is better described relative to track length).
- The `total_duration_seconds=0.0` fallback means no new parameter is required at existing call sites. The only caller that passes a real duration is `analyze_beats_for_folder` and `detect_beat_timestamps`.
- `librosa.get_duration(path=path)` reads from audio container headers without decoding. It is fast and does not increase peak memory.
- The `beat_index` field in the emitted cue dict for a time-fraction cue holds the **resolved** beat index (the nearest beat), not `None`. This is consistent with how `beat_index` is used downstream (stored in `cue_points.beat_index`).
- Time-fraction cues are skipped if no detected beat falls within **2.0 seconds** of the target position (sparse beat grid safety valve).
- Time-fraction cues that resolve to the same beat index as a previously emitted cue are skipped (dedup — only the first cue for a given beat position is kept). This applies against all previously emitted cues in the same proposal, including beat-indexed ones.
- `_normalized_cue_template` rejects `CueTemplate` instances with **both** `beat_index` and `time_fraction` set (in addition to the existing rejection of neither set).
- All existing presets (starter, phrase, extended) were converted to keyword-argument form: `CueTemplate(cue_label="...", beat_index=N)`. Behavior is identical; the change makes future reading unambiguous.
- Custom `--cue` CLI entries remain beat-index-only. `parse_cue_template` always produces `CueTemplate(cue_label=..., beat_index=N, time_fraction=None)`.

---

## Remaining Backlog (Not Yet Implemented)

### P1 — Should Fix Before Broader Testing

**P1-1 — Separate immutable AI suggestions from approved metadata** *(most important)*
The `tracks` table uses a single set of `normalized_*` columns for both the machine suggestion and the user-approved value. Once a user edits a track, the original suggestion is gone from the table. The fix requires a schema migration adding `suggested_decade`, `suggested_primary_genre`, `suggested_subgenre`, `suggested_dj_use_tags`, `suggestion_confidence` columns (write-once on scan), keeping `normalized_*` as the mutable approved values, and updating scan, review service, export, and UI to use the correct column set for each purpose.
**Files:** `database.py`, `scanner.py` (via `cli.py:_prepare_track`), `review_service.py`, `csv_exporter.py`, `frontend/app.js`, `frontend/index.html`

**P1-2 — Fix Hindi → Bollywood mapping; complete Indian subgenre rules**
The JSON rule in `indian_music.json` still maps `"Hindi"` to `Indian/Bollywood`. The hardcoded `_suggest_genre_match` in `genre_normalizer.py` maps it to `Bollywood/Classic Bollywood` — an improvement but still incorrect (Hindi is a language, not a film industry). The two layers now disagree. The correct fix is `Indian/Hindi` at ~0.55 confidence with `needs_review`. Also missing: Indian wedding keyword rule, Telugu/Marathi/Gujarati rules. The `indian_music.json` rule should be updated to match the hardcoded logic (or the hardcoded logic should be removed in favour of JSON rules — see P1-3 below).
**Files:** `rules/indian_music.json`, `genre_normalizer.py`, `tests/test_genre_normalizer.py`

**P1-3 — Consolidate genre matching: remove hardcoded special cases, use JSON rules**
`genre_normalizer.py` grew a large hardcoded `_suggest_genre_match` block that now handles most genres (Pop, Dance, EDM, R&B subgenres, Hip-Hop subgenres, Latin subgenres, Indian subgenres). The JSON rule files have not been updated to match. The two layers can produce different results for the same input (notably for Hindi, as above). Country has no rule anywhere. The right fix is to move all genre matching into JSON rules and remove the hardcoded block (or clearly document which layer is authoritative and keep them in sync). Currently the hardcoded block is the de facto primary source; the JSON rules are only reached via the `normalize_context` fallback.
**Files:** `genre_normalizer.py`, `rules/general_genres.json`, `rules/latin_music.json`, `rules/indian_music.json`, `tests/test_genre_normalizer.py`

**P1-4 — Fix "edit" and "intro" keyword rule false positives**
`rules/dj_utility_tags.json`: The `keyword-remix` rule uses `"edit"` as a bare `contains` match. Any track with "edit" anywhere in its metadata gets the `remix-edit` tag — including "Editor's Cut", "Unedited Version", etc. Same problem with `"intro"` matching "Introduction to Jazz". Fix: tighten the match values to require parenthetical or suffix form, e.g. `"(edit)"`, `"(radio edit)"`, `"(intro)"`. Consider adding word-boundary matching support to `genre_normalizer.py`'s `_rule_matches`.
**Files:** `rules/dj_utility_tags.json`, `genre_normalizer.py` (optional), `tests/test_genre_normalizer.py`

**P1-5 — Export-event audit logging**
After a successful export, no record is written to the database. A DJ cannot query whether a specific track was exported, when, or what the export path was. Fix: write one row per exported track to `review_history` (action = "exported", source = "csv_export" or "json_export") or a new `export_log` table. The export UUID is already generated per export run in `csv_exporter.py` — use it as the correlation ID.
**Files:** `csv_exporter.py`, `database.py`

---

### P2 — Useful MVP Improvements

**P2-1 — Bulk approve/reject/skip in review UI**
`database.py:_infer_review_action` already contains a stub for `source == "bulk_action"`. What's missing: a `POST /api/tracks/bulk-update` endpoint in `local_api.py`, a service-layer bulk update handler in `review_service.py`, and UI checkbox selection + bulk action controls in `frontend/`.

**P2-2 — Confidence-score filter in review UI**
`GET /api/tracks` accepts only a `status` filter. Add `max_confidence` query param to the API and a confidence slider to the UI.

**P2-3 — Per-cue review workflow**
`cue_points.review_status` is written by the analyzer but never updated by user action. Add `PATCH /api/cue-points/{id}` and UI controls. Log changes to `review_history`.

**P2-4 — Consolidate correction_history into review_history**
CSV imports write to both tables. `correction_history` is a legacy lighter-weight table that predates `review_history`. Stop writing to `correction_history` (keep the table to avoid breaking existing databases), add a migration that copies pre-existing rows to `review_history`.

**P2-5 — Half-time / double-time BPM sanity check**
`librosa.beat.beat_track()` frequently returns half or double the musical BPM. Add post-detection logic in `bpm_analyzer.py` that checks whether the result falls in a suspicious range relative to the track's genre (if known) and flags it with a `bpm_note` or `needs_review` override.

---

### P3 — Future / Not Yet

- P3-1: Safe metadata write-back — design/research only, no code yet
- P3-2: Engine DJ / Rekordbox / MIXO adapters — research only
- P3-3: Bulk cue write-back — do not build (accuracy not ready)
- P3-4: MusicBrainz / AcoustID lookup
- P3-5: Desktop wrapper (Tauri / Electron)

---

## Architecture Notes for Codex

**How the genre normalizer works (two-layer design):**
`suggest_track_metadata()` → calls `_suggest_genre_match()` (hardcoded Python cascade) → if no match, falls back to `normalize_context()` (JSON rules). `normalize_genre()` → calls `normalize_context()` directly (JSON rules only). Both paths exist; CLI scan uses `suggest_track_metadata`, `normalize_context` is the JSON-rule-only path. The hardcoded block now covers most genres, making the JSON rules largely redundant for those cases. This inconsistency is the core issue in P1-3.

**How the BPM skip guard works:**
In `bpm_analyzer.py`, `_ensure_track()` fetches the track from DB (or inserts it if new). The returned `Track` object has `.review_status` as a `ReviewStatus` enum. The guard checks `track.review_status.value in REVIEWED_STATUSES` before calling `detect_bpm()`. The `.value` access converts the enum to its string form for the frozenset comparison.

**Schema migration pattern:**
`database.py:_run_migrations()` reads `PRAGMA user_version`, then runs each `(target_version, migration_fn)` pair in `MIGRATIONS` where `target_version > schema_version`. Each migration function uses `_ensure_column()` for ADD COLUMN operations or direct `connection.execute()` for other DDL. After each migration, `PRAGMA user_version` is updated. When adding a new migration: (1) increment `CURRENT_SCHEMA_VERSION`, (2) write a new `_migrate_*` function, (3) append `(CURRENT_SCHEMA_VERSION, _migrate_*)` to `MIGRATIONS`, (4) write a test in `test_database.py` that creates a pre-migration database and verifies the post-migration state.

**Test fixtures:**
`conftest.py` overrides `tmp_path` to write to `.test-tmp/` in the project root for easier debugging. All tests use `tmp_path` for file system isolation. BPM and beat tests use `monkeypatch` to stub `detect_bpm` and `detect_beat_timestamps` — these functions require `librosa` which is not installed in CI.

**Safety invariant:**
No file in the codebase calls `mutagen`'s `.save()` or any equivalent write method. The only writes are to the local SQLite database and to user-specified export output paths. This invariant must be maintained. Any future write-back feature must go through a deliberate design review (see P3-1 in the backlog).
