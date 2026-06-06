from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dj_library_prep import database
from dj_library_prep.metadata import read_track_metadata
from dj_library_prep.models import ReviewStatus, Track
from dj_library_prep.scanner import scan_audio_files


LOW_CONFIDENCE_THRESHOLD = 0.6
REVIEWED_STATUSES = frozenset({"approved", "edited"})


@dataclass(frozen=True, slots=True)
class BpmResult:
    bpm: float | None
    confidence: float


@dataclass(frozen=True, slots=True)
class BpmAnalysisSummary:
    total_files: int
    analyzed_tracks: int
    tracks_needing_review: int
    failed_tracks: int
    skipped_reviewed_tracks: int = 0


def analyze_bpm_for_folder(
    folder: str | Path,
    database_path: str | Path = "djcuecraft.sqlite3",
    *,
    force: bool = False,
) -> BpmAnalysisSummary:
    audio_files = scan_audio_files(folder)
    analyzed_tracks = 0
    tracks_needing_review = 0
    failed_tracks = 0
    skipped_reviewed_tracks = 0

    with database.connect(database_path) as connection:
        for path in audio_files:
            track = _ensure_track(connection, path)

            if not force and track.review_status.value in REVIEWED_STATUSES:
                skipped_reviewed_tracks += 1
                continue

            result = detect_bpm(path)
            if result.bpm is None:
                failed_tracks += 1

            review_status = (
                ReviewStatus.NEEDS_REVIEW
                if result.confidence < LOW_CONFIDENCE_THRESHOLD
                else track.review_status
            )
            if review_status == ReviewStatus.NEEDS_REVIEW:
                tracks_needing_review += 1

            database.update_track_bpm(
                connection=connection,
                file_path=track.file_path,
                bpm=result.bpm,
                bpm_confidence=result.confidence,
                review_status=review_status.value,
            )
            analyzed_tracks += 1
        connection.commit()

    return BpmAnalysisSummary(
        total_files=len(audio_files),
        analyzed_tracks=analyzed_tracks,
        tracks_needing_review=tracks_needing_review,
        failed_tracks=failed_tracks,
        skipped_reviewed_tracks=skipped_reviewed_tracks,
    )


def detect_bpm(path: str | Path) -> BpmResult:
    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError(
            "BPM analysis requires the optional audio dependency `librosa`. "
            "Install it with: python -m pip install -e \".[audio,dev]\""
        ) from exc

    try:
        # 120s sample is sufficient for BPM; beat_analyzer loads the full track
        audio, sample_rate = librosa.load(path, mono=True, duration=120)
        onset_envelope = librosa.onset.onset_strength(y=audio, sr=sample_rate)
        tempo = librosa.feature.tempo(onset_envelope=onset_envelope, sr=sample_rate)
    except Exception:
        return BpmResult(bpm=None, confidence=0.0)

    bpm = _first_number(tempo)
    if bpm is None or bpm <= 0:
        return BpmResult(bpm=None, confidence=0.0)

    confidence = _estimate_confidence(onset_envelope)
    return BpmResult(bpm=round(float(bpm), 2), confidence=confidence)


def _ensure_track(connection: Any, path: Path) -> Track:
    existing = database.get_track_by_file_path(connection, str(path))
    if existing is not None:
        return _track_from_row(existing)

    track = read_track_metadata(path)
    database.save_track(connection, track)
    saved = database.get_track_by_file_path(connection, str(path))
    if saved is None:
        return track
    return _track_from_row(saved)


def _track_from_row(row: Any) -> Track:
    return Track(
        id=row["id"],
        file_path=row["file_path"],
        file_name=row["file_name"],
        file_extension=row["file_extension"],
        artist=row["artist"],
        title=row["title"],
        album=row["album"],
        year=row["year"],
        original_genre=row["original_genre"],
        normalized_decade=row["normalized_decade"],
        normalized_primary_genre=row["normalized_primary_genre"],
        normalized_subgenre=row["normalized_subgenre"],
        metadata_confidence=row["metadata_confidence"],
        genre_confidence=row["genre_confidence"],
        bpm=row["bpm"],
        bpm_confidence=row["bpm_confidence"],
        review_status=row["review_status"],
    )


def _first_number(value: Any) -> float | None:
    try:
        if hasattr(value, "__len__"):
            return float(value[0])
        return float(value)
    except (TypeError, ValueError, IndexError):
        return None


def _estimate_confidence(onset_envelope: Any) -> float:
    try:
        import numpy as np

        if len(onset_envelope) == 0:
            return 0.0
        mean = float(np.mean(onset_envelope))
        maximum = float(np.max(onset_envelope))
    except Exception:
        return 0.0

    if maximum <= 0:
        return 0.0
    contrast = max(0.0, min(1.0, (maximum - mean) / maximum))
    return round(contrast, 3)
