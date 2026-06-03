from __future__ import annotations

from pathlib import Path
from typing import Any

from dj_library_prep.models import Track

try:
    from mutagen import File as MutagenFile
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    MutagenFile = None


FIELD_KEYS = {
    "artist": ("artist", "albumartist", "\xa9ART", "TPE1"),
    "title": ("title", "\xa9nam", "TIT2"),
    "album": ("album", "\xa9alb", "TALB"),
    "year": ("date", "year", "\xa9day", "TDRC", "TYER"),
    "original_genre": ("genre", "\xa9gen", "TCON"),
}


def read_track_metadata(path: str | Path) -> Track:
    audio_path = Path(path)
    track = Track.from_file(audio_path)

    if MutagenFile is None:
        return track

    try:
        audio = MutagenFile(audio_path, easy=True)
    except Exception:
        return track

    if audio is None or not audio.tags:
        return track

    metadata_values = {
        field: _first_tag_value(audio.tags, keys) for field, keys in FIELD_KEYS.items()
    }

    track.artist = metadata_values["artist"]
    track.title = metadata_values["title"]
    track.album = metadata_values["album"]
    track.year = metadata_values["year"]
    track.original_genre = metadata_values["original_genre"]
    track.metadata_confidence = _metadata_confidence(track)
    return track


def _first_tag_value(tags: Any, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = tags.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            value = value[0] if value else None
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return None


def _metadata_confidence(track: Track) -> float:
    fields = [track.artist, track.title, track.year, track.original_genre]
    present = sum(1 for value in fields if value)
    return present / len(fields)
