"""Per-track cue pad management.

Pads are a fixed grid of 8 slots per track. They are stored in the local
SQLite ``pads`` table only. Like every other DJ CueCraft output, pads are
proposals for review and are never written to audio files or DJ software.

Auto-fill places pads at phrase boundaries derived from stored beat
timestamps. It preserves any pad the user has touched (``source = 'manual'``)
and only writes empty slots or slots that are still ``source = 'auto'``.
"""

from __future__ import annotations

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
    """Create or update a single pad as a manual (user-owned) pad.

    Used for both renaming (label only) and re-capturing a position
    (timestamp_seconds). Existing values are preserved when an argument is
    omitted so a rename does not wipe the captured time, and vice versa.
    """
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
            # Re-capture from playhead: the beat index no longer applies.
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
    database_path: str | Path = "djcuecraft.sqlite3",
) -> list[dict[str, Any]]:
    """Place phrase-based pads from stored beat timestamps.

    Pads land on beats 0, phrase_length, 2*phrase_length, ... Manual pads are
    preserved; only empty or still-auto slots are (re)written. Raises
    ValueError when the track has no stored beats yet.
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

    return list_pads_for_track(track_id, database_path)


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
