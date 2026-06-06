from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dj_library_prep import database
from dj_library_prep.bpm_analyzer import _ensure_track
from dj_library_prep.models import ReviewStatus
from dj_library_prep.scanner import scan_audio_files


LOW_CUE_CONFIDENCE_THRESHOLD = 0.6
DEFAULT_CUE_PRESET = "performance"


@dataclass(frozen=True, slots=True)
class CueTemplate:
    cue_label: str
    beat_index: int | None = None
    time_fraction: float | None = None


CUE_PRESETS: dict[str, tuple[CueTemplate, ...]] = {
    "starter": (
        CueTemplate("Intro", 0),
        CueTemplate("8 Beats In", 8),
        CueTemplate("16 Beats In", 16),
        CueTemplate("32 Beats In", 32),
        CueTemplate("64 Beats In", 64),
    ),
    "phrase": (
        CueTemplate("Intro", 0),
        CueTemplate("Phrase 1", 32),
        CueTemplate("Phrase 2", 64),
        CueTemplate("Phrase 3", 96),
        CueTemplate("Phrase 4", 128),
    ),
    "extended": (
        CueTemplate("Intro", 0),
        CueTemplate("8 Beats In", 8),
        CueTemplate("16 Beats In", 16),
        CueTemplate("32 Beats In", 32),
        CueTemplate("64 Beats In", 64),
        CueTemplate("96 Beats In", 96),
        CueTemplate("128 Beats In", 128),
    ),
    "performance": (
        CueTemplate("Intro", 0),
        CueTemplate("8 Beats In", 8),
        CueTemplate("32 Beats In", 32),
        CueTemplate("64 Beats In", 64),
        CueTemplate("128 Beats In", 128),
        CueTemplate("Breakdown", time_fraction=0.40),
        CueTemplate("Build", time_fraction=0.70),
        CueTemplate("Outro", time_fraction=0.88),
    ),
    "minimix": (
        CueTemplate("Intro", 0),
        CueTemplate("1/4", time_fraction=0.25),
        CueTemplate("Mid", time_fraction=0.50),
        CueTemplate("3/4", time_fraction=0.75),
        CueTemplate("Outro Prep", time_fraction=0.85),
        CueTemplate("Outro", time_fraction=0.90),
        CueTemplate("Exit", time_fraction=0.95),
        CueTemplate("End", time_fraction=0.99),
    ),
}

CueTemplateInput = CueTemplate | tuple[str, int]
CueTemplateCollection = Iterable[CueTemplateInput]


CUE_TEMPLATE_HELP = (
    "Cue template entries use LABEL=BEAT_INDEX, for example "
    "'Drop Prep=32'. Repeat --cue to define multiple cues."
)


@dataclass(frozen=True, slots=True)
class BeatAnalysisResult:
    beat_timestamps: list[float]
    beat_confidence: float
    total_duration_seconds: float = 0.0


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
    cue_template: CueTemplateCollection | None = None,
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
                # Detection failed: preserve any previously stored beats and
                # cue points for this track instead of overwriting them.
                failed_tracks += 1
                continue

            cues = propose_cue_points(
                result.beat_timestamps,
                result.beat_confidence,
                cue_template=cue_template,
                total_duration_seconds=result.total_duration_seconds,
            )
            stored_beats += database.replace_beat_timestamps(
                connection=connection,
                track_id=track.id,
                file_path=track.file_path,
                beat_timestamps=result.beat_timestamps,
                beat_confidence=result.beat_confidence,
            )
            inserted_cues = database.insert_missing_cue_points(
                connection=connection,
                track_id=track.id,
                file_path=track.file_path,
                cue_points=cues,
            )
            proposed_cue_points += len(inserted_cues)
            cue_points_needing_review += sum(
                1
                for cue in inserted_cues
                if cue["review_status"] == ReviewStatus.NEEDS_REVIEW.value
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
        total_duration_seconds = float(librosa.get_duration(path=path))
        audio, sample_rate = librosa.load(path, mono=True, duration=180)
        onset_envelope = librosa.onset.onset_strength(y=audio, sr=sample_rate)
        _, beat_frames = librosa.beat.beat_track(
            y=audio,
            sr=sample_rate,
            onset_envelope=onset_envelope,
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sample_rate)
    except Exception:
        return BeatAnalysisResult(beat_timestamps=[], beat_confidence=0.0, total_duration_seconds=0.0)

    confidence = _estimate_beat_confidence(onset_envelope, beat_frames)
    return BeatAnalysisResult(
        beat_timestamps=[round(float(beat_time), 3) for beat_time in beat_times],
        beat_confidence=confidence,
        total_duration_seconds=total_duration_seconds,
    )


def propose_cue_points(
    beat_timestamps: list[float],
    beat_confidence: float,
    cue_template: CueTemplateCollection | None = None,
    total_duration_seconds: float | None = None,
) -> list[dict[str, object]]:
    review_status = (
        ReviewStatus.NEEDS_REVIEW
        if beat_confidence < LOW_CUE_CONFIDENCE_THRESHOLD
        else ReviewStatus.PENDING
    )
    cue_points: list[dict[str, object]] = []
    for cue_template_item in _normalized_cue_template(cue_template):
        if cue_template_item.time_fraction is not None:
            if not total_duration_seconds or not beat_timestamps:
                continue
            target_time = cue_template_item.time_fraction * total_duration_seconds
            beat_index = _nearest_beat_index(beat_timestamps, target_time)
            timestamp = beat_timestamps[beat_index]
        else:
            beat_index = cue_template_item.beat_index  # type: ignore[assignment]
            if beat_index >= len(beat_timestamps):
                continue
            timestamp = beat_timestamps[beat_index]
        cue_points.append(
            {
                "cue_label": cue_template_item.cue_label,
                "beat_index": beat_index,
                "timestamp_seconds": timestamp,
                "cue_confidence": beat_confidence,
                "review_status": review_status.value,
            }
        )
    return cue_points


def cue_template_for_preset(preset_name: str) -> tuple[CueTemplate, ...]:
    try:
        return CUE_PRESETS[preset_name]
    except KeyError as exc:
        available = ", ".join(sorted(CUE_PRESETS))
        raise ValueError(
            f"Unknown cue preset: {preset_name}. Available presets: {available}"
        ) from exc


def parse_cue_template(cue_specs: Iterable[str]) -> tuple[CueTemplate, ...]:
    cues = []
    for cue_spec in cue_specs:
        if "=" not in cue_spec:
            raise ValueError(f"Invalid cue template entry: {cue_spec}. {CUE_TEMPLATE_HELP}")
        label, beat_index = cue_spec.split("=", 1)
        label = label.strip()
        beat_index = beat_index.strip()
        if not label:
            raise ValueError("Cue labels cannot be blank.")
        try:
            cues.append(CueTemplate(label, int(beat_index)))
        except ValueError as exc:
            raise ValueError(
                f"Cue beat index must be an integer: {cue_spec}"
            ) from exc

    return _normalized_cue_template(cues)


def _normalized_cue_template(
    cue_template: CueTemplateCollection | None,
) -> tuple[CueTemplate, ...]:
    raw_template = (
        cue_template
        if cue_template is not None
        else cue_template_for_preset(DEFAULT_CUE_PRESET)
    )
    normalized = tuple(_coerce_cue_template_item(item) for item in raw_template)
    if not normalized:
        raise ValueError("Cue template must include at least one cue.")

    labels = set()
    for cue in normalized:
        if cue.beat_index is None and cue.time_fraction is None:
            raise ValueError(
                f"CueTemplate must specify beat_index or time_fraction: {cue.cue_label}"
            )
        if cue.beat_index is not None and cue.beat_index < 0:
            raise ValueError(f"Cue beat index cannot be negative: {cue.cue_label}")
        if cue.time_fraction is not None and not (0.0 <= cue.time_fraction <= 1.0):
            raise ValueError(
                f"Cue time_fraction must be between 0.0 and 1.0: {cue.cue_label}"
            )
        if cue.cue_label in labels:
            raise ValueError(f"Duplicate cue label: {cue.cue_label}")
        labels.add(cue.cue_label)
    return normalized


def _coerce_cue_template_item(item: CueTemplateInput) -> CueTemplate:
    if isinstance(item, CueTemplate):
        return item
    label, beat_index = item
    return CueTemplate(str(label), int(beat_index))


def _nearest_beat_index(beat_timestamps: list[float], target_time: float) -> int:
    return min(range(len(beat_timestamps)), key=lambda i: abs(beat_timestamps[i] - target_time))


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
