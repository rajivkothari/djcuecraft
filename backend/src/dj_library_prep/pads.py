"""Per-track cue pad management.

Pads are a fixed grid of 8 slots per track. They are stored in the local
SQLite ``pads`` table only. Like every other DJ CueCraft output, pads are
proposals for review and are never written to audio files or DJ software.

Auto-fill supports two modes:
- Phrase-based (default): pads at beats 0, phrase_length, 2*phrase_length, …
- Preset-based: uses a named CUE_PRESETS entry; beat-indexed cues are placed
  by beat count from the start, time-fraction cues are resolved to the nearest
  beat using the caller-supplied total_duration_seconds.

Manual pads (source='manual') are always preserved in both modes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from dj_library_prep import database


PAD_COUNT = 8
DEFAULT_PHRASE_LENGTH = 32

SOURCE_AUTO = "auto"
SOURCE_MANUAL = "manual"


def list_pads_for_track(
    track_id: int,
    database_path: str | Path = "djcuecraft.sqlite3",
) -> list[dict[str, Any]]:
    """Return all 8 pad slots for a track, filling empty slots with blanks."""
    with database.connect(database_path) as connection:
        rows = {row["pad_index"]: dict(row) for row in database.list_pads(connection, track_id)}
    return [rows.get(index, _empty_pad(track_id, index)) for index in range(PAD_COUNT)]


def set_pad(
    track_id: int,
    pad_index: int,
    *,
    label: str | None = None,
    timestamp_seconds: float | None = None,
    beat_index: int | None = None,
    database_path: str | Path = "djcuecraft.sqlite3",
) -> dict[str, Any]:
    """Create or update a single pad as a manual (user-owned) pad."""
    _validate_pad_index(pad_index)

    with database.connect(database_path) as connection:
        existing = database.get_pad(connection, track_id, pad_index)

        new_label = label if label is not None else (existing["label"] if existing else f"Pad {pad_index + 1}")
        new_label = str(new_label).strip()
        if not new_label:
            raise ValueError("Pad label must not be empty.")

        if timestamp_seconds is not None:
            new_timestamp: float | None = float(timestamp_seconds)
            if new_timestamp < 0:
                raise ValueError("Pad timestamp must not be negative.")
        else:
            new_timestamp = existing["timestamp_seconds"] if existing else None

        if beat_index is not None:
            new_beat: int | None = int(beat_index)
        elif timestamp_seconds is not None:
            new_beat = None
        else:
            new_beat = existing["beat_index"] if existing else None

        updated = database.upsert_pad(
            connection,
            track_id=track_id,
            pad_index=pad_index,
            label=new_label,
            timestamp_seconds=new_timestamp,
            beat_index=new_beat,
            source=SOURCE_MANUAL,
        )
    return dict(updated) if updated is not None else _empty_pad(track_id, pad_index)


def clear_pad(
    track_id: int,
    pad_index: int,
    database_path: str | Path = "djcuecraft.sqlite3",
) -> None:
    _validate_pad_index(pad_index)
    with database.connect(database_path) as connection:
        database.clear_pad(connection, track_id, pad_index)


def clear_all_pads(
    track_id: int,
    database_path: str | Path = "djcuecraft.sqlite3",
) -> list[dict[str, Any]]:
    with database.connect(database_path) as connection:
        database.clear_all_pads(connection, track_id)
    return list_pads_for_track(track_id, database_path)


def autofill_pads(
    track_id: int,
    *,
    phrase_length: int = DEFAULT_PHRASE_LENGTH,
    preset_name: str | None = None,
    total_duration_seconds: float | None = None,
    database_path: str | Path = "djcuecraft.sqlite3",
) -> list[dict[str, Any]]:
    """Place pads from stored beat timestamps.

    When ``preset_name`` is given the named CUE_PRESETS entry drives the
    labels and positions; time-fraction cues in the preset resolve to the
    nearest beat using ``total_duration_seconds`` (silently skipped when it
    is not supplied). When ``preset_name`` is None the classic phrase-based
    mode is used (pads at beats 0, phrase_length, 2*phrase_length, …).

    Manual pads are preserved in both modes. Raises ValueError when the
    track has no stored beats yet.
    """
    if phrase_length <= 0:
        raise ValueError("Phrase length must be a positive number of beats.")

    with database.connect(database_path) as connection:
        beats = database.list_beat_timestamps_for_track(connection, track_id)
        if not beats:
            raise ValueError(
                "No beats stored for this track yet. Run Analyze first to detect beats."
            )

        existing = {row["pad_index"]: row for row in database.list_pads(connection, track_id)}
        if preset_name is not None:
            _autofill_from_preset(
                connection, track_id, preset_name, beats, total_duration_seconds, existing
            )
        else:
            _autofill_from_phrase(connection, track_id, phrase_length, beats, existing)

    return list_pads_for_track(track_id, database_path)


def batch_autofill_pads(
    *,
    phrase_length: int = DEFAULT_PHRASE_LENGTH,
    skip_existing: bool = True,
    database_path: str | Path = "djcuecraft.sqlite3",
) -> dict[str, int]:
    """Auto-fill pads for every track that has stored beats.

    When *skip_existing* is True (the default), tracks that already have at
    least one filled pad are left untouched.  Raises ValueError for an invalid
    phrase_length.  Each track is processed independently; an error on one
    track is counted and does not stop the batch.
    """
    if phrase_length <= 0:
        raise ValueError("Phrase length must be a positive number of beats.")

    with database.connect(database_path) as connection:
        tracks = list(database.list_tracks(connection))

    total_tracks = len(tracks)
    filled = 0
    skipped_existing = 0
    skipped_no_beats = 0
    failed = 0

    for track in tracks:
        track_id = int(track["id"])
        try:
            with database.connect(database_path) as connection:
                beats = database.list_beat_timestamps_for_track(connection, track_id)
                if not beats:
                    skipped_no_beats += 1
                    continue
                if skip_existing and database.count_filled_pads(connection, track_id) > 0:
                    skipped_existing += 1
                    continue
            autofill_pads(track_id, phrase_length=phrase_length, database_path=database_path)
            filled += 1
        except Exception:
            failed += 1

    return {
        "total_tracks": total_tracks,
        "filled": filled,
        "skipped_existing_pads": skipped_existing,
        "skipped_no_beats": skipped_no_beats,
        "failed": failed,
    }


def _autofill_from_phrase(
    connection: sqlite3.Connection,
    track_id: int,
    phrase_length: int,
    beats: list[float],
    existing: dict[int, Any],
) -> None:
    for pad_index in range(PAD_COUNT):
        current = existing.get(pad_index)
        if current is not None and current["source"] == SOURCE_MANUAL:
            continue

        beat_index = pad_index * phrase_length
        if beat_index >= len(beats):
            continue

        database.upsert_pad(
            connection,
            track_id=track_id,
            pad_index=pad_index,
            label=_phrase_label(pad_index),
            timestamp_seconds=beats[beat_index],
            beat_index=beat_index,
            source=SOURCE_AUTO,
        )


def _autofill_from_preset(
    connection: sqlite3.Connection,
    track_id: int,
    preset_name: str,
    beats: list[float],
    total_duration_seconds: float | None,
    existing: dict[int, Any],
) -> None:
    from dj_library_prep.beat_analyzer import CUE_PRESETS, _nearest_beat_index

    try:
        preset = CUE_PRESETS[preset_name]
    except KeyError:
        available = ", ".join(sorted(CUE_PRESETS))
        raise ValueError(f"Unknown preset: {preset_name}. Available: {available}")

    for pad_index, cue in enumerate(preset):
        if pad_index >= PAD_COUNT:
            break

        current = existing.get(pad_index)
        if current is not None and current["source"] == SOURCE_MANUAL:
            continue

        if cue.time_fraction is not None:
            if not total_duration_seconds or not beats:
                continue
            target_time = cue.time_fraction * total_duration_seconds
            beat_index = _nearest_beat_index(beats, target_time)
            timestamp = beats[beat_index]
        else:
            beat_index = cue.beat_index  # type: ignore[assignment]
            if beat_index >= len(beats):
                continue
            timestamp = beats[beat_index]

        database.upsert_pad(
            connection,
            track_id=track_id,
            pad_index=pad_index,
            label=cue.cue_label,
            timestamp_seconds=timestamp,
            beat_index=beat_index,
            source=SOURCE_AUTO,
        )


def _phrase_label(pad_index: int) -> str:
    if pad_index == 0:
        return "Intro"
    return f"Phrase {pad_index}"


def _empty_pad(track_id: int, pad_index: int) -> dict[str, Any]:
    return {
        "id": None,
        "track_id": track_id,
        "pad_index": pad_index,
        "label": _phrase_label(pad_index),
        "timestamp_seconds": None,
        "beat_index": None,
        "source": None,
        "created_at": None,
        "updated_at": None,
    }


def _validate_pad_index(pad_index: int) -> None:
    if not 0 <= pad_index < PAD_COUNT:
        raise ValueError(f"Pad index must be between 0 and {PAD_COUNT - 1}.")
