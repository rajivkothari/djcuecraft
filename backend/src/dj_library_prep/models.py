from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import json
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".wav"}


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    NEEDS_REVIEW = "needs_review"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_decade(year: int | str | None) -> str:
    if year is None:
        return "Unknown"

    text = str(year).strip()
    if len(text) >= 4 and text[:4].isdigit():
        value = int(text[:4])
    elif text.isdigit():
        value = int(text)
    else:
        return "Unknown"

    if 1970 <= value <= 1979:
        return "70s"
    if 1980 <= value <= 1989:
        return "80s"
    if 1990 <= value <= 1999:
        return "90s"
    if 2000 <= value <= 2009:
        return "00s"
    if 2010 <= value <= 2019:
        return "10s"
    if 2020 <= value <= 2029:
        return "20s"
    return "Unknown"


@dataclass(slots=True)
class Track:
    file_path: str
    file_name: str
    file_extension: str
    id: int | None = None
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    year: str | None = None
    original_genre: str | None = None
    normalized_decade: str = "Unknown"
    normalized_primary_genre: str | None = None
    normalized_subgenre: str | None = None
    dj_use_tags: list[str] = field(default_factory=list)
    metadata_confidence: float = 0.0
    genre_confidence: float = 0.0
    bpm: float | None = None
    bpm_confidence: float = 0.0
    review_status: ReviewStatus = ReviewStatus.PENDING
    suggested_decade: str | None = None
    suggested_primary_genre: str | None = None
    suggested_subgenre: str | None = None
    suggested_dj_use_tags: list[str] = field(default_factory=list)
    suggestion_confidence: float = 0.0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        self.file_extension = self.file_extension.lower()
        if self.file_extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported audio extension: {self.file_extension}")
        if not isinstance(self.review_status, ReviewStatus):
            self.review_status = ReviewStatus(str(self.review_status))
        self.metadata_confidence = _bounded_confidence(self.metadata_confidence)
        self.genre_confidence = _bounded_confidence(self.genre_confidence)
        self.bpm_confidence = _bounded_confidence(self.bpm_confidence)

    @classmethod
    def from_file(cls, path: Path) -> "Track":
        return cls(
            file_path=str(path),
            file_name=path.name,
            file_extension=path.suffix.lower(),
            review_status=ReviewStatus.NEEDS_REVIEW,
        )

    def missing_fields(self) -> list[str]:
        missing = []
        for field_name in ("artist", "title", "year", "original_genre"):
            if not getattr(self, field_name):
                missing.append(field_name)
        return missing

    def to_db_row(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_extension": self.file_extension,
            "artist": self.artist,
            "title": self.title,
            "album": self.album,
            "year": self.year,
            "original_genre": self.original_genre,
            "normalized_decade": self.normalized_decade,
            "normalized_primary_genre": self.normalized_primary_genre,
            "normalized_subgenre": self.normalized_subgenre,
            "dj_use_tags": json.dumps(self.dj_use_tags),
            "metadata_confidence": self.metadata_confidence,
            "genre_confidence": self.genre_confidence,
            "bpm": self.bpm,
            "bpm_confidence": self.bpm_confidence,
            "review_status": self.review_status.value,
            "suggested_decade": self.suggested_decade,
            "suggested_primary_genre": self.suggested_primary_genre,
            "suggested_subgenre": self.suggested_subgenre,
            "suggested_dj_use_tags": json.dumps(self.suggested_dj_use_tags),
            "suggestion_confidence": self.suggestion_confidence if self.suggestion_confidence else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def _bounded_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
