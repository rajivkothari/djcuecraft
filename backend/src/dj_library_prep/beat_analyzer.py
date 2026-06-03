from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dj_library_prep import database
from dj_library_prep.bpm_analyzer import _ensure_track
from dj_library_prep.models import ReviewStatus
from dj_library_prep.scanner import scan_audio_files


LOW_CUE_CONFIDENCE_THRESHOLD = 0.6
CUE_BEAT_OFFSETS = (
    ("Intro", 0),
    ("8 Beats In", 8),
    ("16 Beats In", 16),
    ("32 Beats In", 32),
    ("64 Beats In", 64),
)


@dataclass(frozen=True, slots=True)
class BeatAnalysisResult:
    beat_timestamps: list[float]
    beat_confidence: float


@dataclass(frozen=True, slots=True)
class BeatCueAnalysisSummary:
    total_files: int
    analyzed_tracks: int
    stored_beats: int
    proposed_cue_points: int
    cue_points_needing_review: int
    failed_tracks: int


def analyze_beats_for_folder(
    folder: str | Path,
    database_path: str | Path = "djcuecraft.sqlite3",
) -> BeatCueAnalysisSummary:
    audio_files = scan_audio_files(folder)
    analyzed_tracks = 0
    stored_beats = 0
    proposed_cue_points = 0
    cue_points_needing_review = 0
    failed_tracks = 0

    with database.connect(database_path) as connection:
        for path in audio_files:
            track = _ensure_track(connection, path)
            result = detect_beat_timestamps(path)
            if not result.beat_timestamps:
                failed_tracks += 1

            cues = propose_cue_points(result.beat_timestamps, result.beat_confidence)
            stored_beats += database.replace_beat_timestamps(
                connection=connection,
                track_id=track.id,
                file_path=track.file_path,
                beat_timestamps=result.beat_timestamps,
                beat_confidence=result.beat_confidence,
            )
            proposed_cue_points += database.replace_cue_points(
                connection=connection,
                track_id=track.id,
                file_path=track.file_path,
                cue_points=cues,
            )
            cue_points_needing_review += sum(
                1 for cue in cues if cue["review_status"] == ReviewStatus.NEEDS_REVIEW.value
            )
            analyzed_tracks += 1
        connection.commit()

    return BeatCueAnalysisSummary(
        total_files=len(audio_files),
        analyzed_tracks=analyzed_tracks,
        stored_beats=stored_beats,
        proposed_cue_points=proposed_cue_points,
        cue_points_needing_review=cue_points_needing_review,
        failed_tracks=failed_tracks,
    )


def detect_beat_timestamps(path: str | Path) -> BeatAnalysisResult:
    try:
        import librosa
    except ImportError as exc:
        raise RuntimeError(
            "Beat analysis requires the optional audio dependency `librosa`. "
            "Install it with: python -m pip install -e \".[audio,dev]\""
        ) from exc

    try:
        audio, sample_rate = librosa.load(path, mono=True, duration=180)
        onset_envelope = librosa.onset.onset_strength(y=audio, sr=sample_rate)
        _, beat_frames = librosa.beat.beat_track(
            y=audio,
            sr=sample_rate,
            onset_envelope=onset_envelope,
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate)
    except Exception:
        return BeatAnalysisResult(beat_timestamps=[], beat_confidence=0.0)

    confidence = _estimate_beat_confidence(onset_envelope, beat_frames)
    return BeatAnalysisResult(
        beat_timestamps=[round(float(beat_time), 3) for beat_time in beat_times],
        beat_confidence=confidence,
    )


def propose_cue_points(
    beat_timestamps: list[float],
    beat_confidence: float,
) -> list[dict[str, object]]:
    review_status = (
        ReviewStatus.NEEDS_REVIEW
        if beat_confidence < LOW_CUE_CONFIDENCE_THRESHOLD
        else ReviewStatus.PENDING
    )
    cue_points: list[dict[str, object]] = []
    for label, beat_index in CUE_BEAT_OFFSETS:
        if beat_index >= len(beat_timestamps):
            continue
        cue_points.append(
            {
                "cue_label": label,
                "beat_index": beat_index,
                "timestamp_seconds": beat_timestamps[beat_index],
                "cue_confidence": beat_confidence,
                "review_status": review_status.value,
            }
        )
    return cue_points


def _estimate_beat_confidence(onset_envelope: Any, beat_frames: Any) -> float:
    try:
        import numpy as np

        if len(onset_envelope) == 0 or len(beat_frames) == 0:
            return 0.0
        beat_strengths = onset_envelope[beat_frames]
        mean = float(np.mean(onset_envelope))
        beat_mean = float(np.mean(beat_strengths))
        maximum = float(np.max(onset_envelope))
    except Exception:
        return 0.0

    if maximum <= 0:
        return 0.0
    confidence = max(0.0, min(1.0, (beat_mean - mean) / maximum + 0.5))
    return round(confidence, 3)
