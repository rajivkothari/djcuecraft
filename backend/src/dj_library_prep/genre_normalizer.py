from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
import json
import re
import unicodedata
from typing import Any

from dj_library_prep.models import ReviewStatus, normalize_decade


LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.7
WEAK_EVIDENCE_SOURCES = {"album", "filename", "title"}
BROAD_OR_VAGUE_GENRES = {
    "dance",
    "indian",
    "international",
    "latin",
    "other",
    "soundtrack",
    "unknown",
    "world",
}

RULE_FILES = (
    "general_genres.json",
    "latin_music.json",
    "indian_music.json",
    "dj_utility_tags.json",
)


@dataclass(frozen=True, slots=True)
class GenreNormalization:
    primary_genre: str | None
    subgenre: str | None = None
    dj_use_tags: list[str] = field(default_factory=list)
    confidence: float = 0.0
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    evidence_sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MetadataSuggestion:
    suggested_decade: str
    suggested_genre: str | None
    suggested_subgenre: str | None
    normalized_label: str
    confidence: float
    review_required: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "suggested_decade": self.suggested_decade,
            "suggested_genre": self.suggested_genre,
            "suggested_subgenre": self.suggested_subgenre,
            "normalized_label": self.normalized_label,
            "confidence": self.confidence,
            "review_required": self.review_required,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class TrackNormalizationContext:
    original_genre: str | None = None
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    year: str | int | None = None
    file_name: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizationRule:
    rule_id: str
    field_name: str
    match_type: str
    values: tuple[str, ...]
    primary_genre: str | None
    subgenre: str | None
    dj_use_tags: tuple[str, ...]
    confidence: float
    review_status: ReviewStatus
    requires_context: tuple[str, ...] = ()
    context_subgenre: str | None = None


def normalize_genre(
    original_genre: str | None,
    *,
    artist: str | None = None,
    title: str | None = None,
    file_name: str | None = None,
) -> GenreNormalization:
    context = TrackNormalizationContext(
        original_genre=original_genre,
        artist=artist,
        title=title,
        file_name=file_name,
    )
    return normalize_context(context)


def suggest_track_metadata(
    *,
    original_genre: str | None = None,
    artist: str | None = None,
    title: str | None = None,
    album: str | None = None,
    year: str | int | None = None,
    file_name: str | None = None,
) -> MetadataSuggestion:
    context = TrackNormalizationContext(
        original_genre=original_genre,
        artist=artist,
        title=title,
        album=album,
        year=year,
        file_name=file_name,
    )
    suggested_decade = normalize_decade(year)
    normalization = normalize_context(context)
    confidence = _compute_suggestion_confidence(normalization, suggested_decade, context)
    review_required = _compute_review_required(normalization, confidence, suggested_decade, context)
    normalized_label = _normalized_label(
        suggested_decade,
        normalization.primary_genre,
        normalization.subgenre,
    )
    return MetadataSuggestion(
        suggested_decade=suggested_decade,
        suggested_genre=normalization.primary_genre,
        suggested_subgenre=normalization.subgenre,
        normalized_label=normalized_label,
        confidence=confidence,
        review_required=review_required,
        reason=_compute_suggestion_reason(
            year=year,
            suggested_decade=suggested_decade,
            normalization=normalization,
            confidence=confidence,
            review_required=review_required,
        ),
    )


def normalize_context(context: TrackNormalizationContext) -> GenreNormalization:
    if not _has_any_context(context):
        return GenreNormalization(None, confidence=0.0, review_status=ReviewStatus.NEEDS_REVIEW)

    matches = [rule for rule in _load_rules() if _rule_matches(rule, context)]
    genre_matches = [
        rule
        for rule in matches
        if rule.primary_genre is not None or rule.subgenre is not None or not rule.dj_use_tags
    ]
    tag_matches = [rule for rule in matches if rule.dj_use_tags]

    best = _best_genre_rule(genre_matches)
    tags = _merge_tags(best, tag_matches)

    if best is None:
        return GenreNormalization(None, dj_use_tags=tags, confidence=0.0)

    sources = _evidence_sources(context, best.values)

    review_status = best.review_status
    pure_tag_matches = [r for r in tag_matches if r.primary_genre is None and r.subgenre is None]
    if any(rule.review_status == ReviewStatus.NEEDS_REVIEW for rule in pure_tag_matches):
        review_status = ReviewStatus.NEEDS_REVIEW

    return GenreNormalization(
        primary_genre=best.primary_genre,
        subgenre=best.subgenre,
        dj_use_tags=tags,
        confidence=best.confidence,
        review_status=review_status,
        evidence_sources=sources,
    )


def normalize_track_fields(
    original_genre: str | None,
    year: str | int | None,
    *,
    artist: str | None = None,
    title: str | None = None,
    file_name: str | None = None,
) -> tuple[GenreNormalization, str]:
    return (
        normalize_genre(
            original_genre,
            artist=artist,
            title=title,
            file_name=file_name,
        ),
        normalize_decade(year),
    )


def _compute_suggestion_confidence(
    normalization: GenreNormalization,
    suggested_decade: str,
    context: TrackNormalizationContext,
) -> float:
    confidence = normalization.confidence
    if (
        suggested_decade == "Unknown"
        or normalization.review_status == ReviewStatus.NEEDS_REVIEW
        or _weak_evidence_requires_review(normalization.evidence_sources)
        or _broad_original_genre_requires_review(context, normalization)
    ):
        confidence = min(confidence, LOW_CONFIDENCE_REVIEW_THRESHOLD - 0.01)
    return round(max(0.0, min(1.0, confidence)), 2)


def _compute_review_required(
    normalization: GenreNormalization,
    confidence: float,
    suggested_decade: str,
    context: TrackNormalizationContext,
) -> bool:
    return (
        confidence < LOW_CONFIDENCE_REVIEW_THRESHOLD
        or normalization.review_status == ReviewStatus.NEEDS_REVIEW
        or normalization.primary_genre is None
        or suggested_decade == "Unknown"
        or _weak_evidence_requires_review(normalization.evidence_sources)
        or _broad_original_genre_requires_review(context, normalization)
    )


def _weak_evidence_requires_review(evidence_sources: tuple[str, ...]) -> bool:
    sources = set(evidence_sources)
    return bool(sources) and sources.issubset(WEAK_EVIDENCE_SOURCES)


def _broad_original_genre_requires_review(
    context: TrackNormalizationContext,
    normalization: GenreNormalization,
) -> bool:
    if not context.original_genre or not normalization.primary_genre:
        return False
    if "genre tag" in normalization.evidence_sources:
        return False
    return bool(_broad_original_genre_terms(context.original_genre))


def _broad_original_genre_terms(original_genre: str) -> set[str]:
    candidates = _match_candidates(original_genre, split_genre=True)
    return candidates.intersection(BROAD_OR_VAGUE_GENRES)


def _normalized_label(
    suggested_decade: str,
    suggested_genre: str | None,
    suggested_subgenre: str | None,
) -> str:
    return " / ".join(
        [
            suggested_decade or "Unknown",
            suggested_genre or "Unknown",
            suggested_subgenre or "Unknown",
        ]
    )


def _compute_suggestion_reason(
    *,
    year: str | int | None,
    suggested_decade: str,
    normalization: GenreNormalization,
    confidence: float,
    review_required: bool,
) -> str:
    parts = []
    if suggested_decade == "Unknown":
        parts.append("No valid year was found, so decade is Unknown.")
    else:
        parts.append(f"Year tag indicates {str(year)[:4]} ({suggested_decade}).")

    source_text = _source_text(normalization.evidence_sources)
    if normalization.primary_genre:
        reason_label = normalization.primary_genre.lower()
        parts.append(f"{source_text} matched {reason_label} patterns.")
    else:
        parts.append(f"{source_text} did not match a reliable genre pattern.")

    if review_required:
        parts.append(
            f"Review required because confidence is {confidence:.2f} or the evidence is broad."
        )
    return " ".join(parts)


def _has_context_term(context: TrackNormalizationContext, term: str) -> bool:
    normalized_term = _normalize_text(term)
    for field_name in ("original_genre", "artist", "title", "album", "file_name"):
        value = getattr(context, field_name)
        if not value:
            continue
        if normalized_term in _normalize_text(str(value)):
            return True
    return False


def _evidence_sources(
    context: TrackNormalizationContext,
    terms: tuple[str, ...] | str,
) -> tuple[str, ...]:
    if isinstance(terms, str):
        terms = (terms,)
    normalized_terms = tuple(_normalize_text(term) for term in terms if term)
    if not normalized_terms:
        return ()

    sources = []
    for field_name, label in (
        ("original_genre", "genre tag"),
        ("title", "title"),
        ("album", "album"),
        ("artist", "artist"),
        ("file_name", "filename"),
    ):
        value = getattr(context, field_name)
        if not value:
            continue
        haystack = _normalize_text(str(value))
        candidates = _match_candidates(str(value), split_genre=field_name == "original_genre")
        if any(term in candidates or term in haystack for term in normalized_terms):
            sources.append(label)
    return tuple(dict.fromkeys(sources))


def _source_text(sources: tuple[str, ...]) -> str:
    if not sources:
        return "Available metadata"
    if len(sources) == 1:
        return sources[0].capitalize()
    return ", ".join(sources[:-1]).capitalize() + f" and {sources[-1]}"


@lru_cache(maxsize=1)
def _load_rules() -> tuple[NormalizationRule, ...]:
    loaded: list[NormalizationRule] = []
    for rule_file in RULE_FILES:
        with resources.files("dj_library_prep.rules").joinpath(rule_file).open(
            encoding="utf-8"
        ) as handle:
            raw_rules = json.load(handle)
        loaded.extend(_parse_rule(raw_rule) for raw_rule in raw_rules["rules"])
    return tuple(loaded)


def _parse_rule(raw_rule: dict[str, Any]) -> NormalizationRule:
    return NormalizationRule(
        rule_id=str(raw_rule["id"]),
        field_name=str(raw_rule.get("field", "genre")),
        match_type=str(raw_rule.get("match_type", "exact")),
        values=tuple(str(value) for value in raw_rule.get("values", [])),
        primary_genre=raw_rule.get("normalized_primary_genre"),
        subgenre=raw_rule.get("normalized_subgenre"),
        dj_use_tags=tuple(str(tag) for tag in raw_rule.get("dj_use_tags", [])),
        confidence=float(raw_rule.get("confidence", 0.0)),
        review_status=ReviewStatus(str(raw_rule.get("review_status", "needs_review"))),
        requires_context=tuple(str(v) for v in raw_rule.get("requires_context", [])),
        context_subgenre=raw_rule.get("context_subgenre"),
    )


def _rule_matches(rule: NormalizationRule, context: TrackNormalizationContext) -> bool:
    values = _context_values(rule.field_name, context)
    if not values:
        return False

    field_matched = False
    for value in values:
        candidates = _match_candidates(value, split_genre=rule.field_name == "genre")
        normalized_value = _normalize_text(value)
        for rule_value in rule.values:
            normalized_rule_value = _normalize_text(rule_value)
            if rule.match_type == "exact" and normalized_rule_value in candidates:
                field_matched = True
                break
            if rule.match_type == "contains" and any(
                normalized_rule_value in candidate for candidate in candidates
            ):
                field_matched = True
                break
            if rule.match_type == "word_boundary":
                pattern = r'\b' + re.escape(normalized_rule_value) + r'\b'
                if re.search(pattern, normalized_value):
                    field_matched = True
                    break
        if field_matched:
            break

    if not field_matched:
        return False

    if rule.requires_context:
        if not any(_has_context_term(context, cv) for cv in rule.requires_context):
            return False

    return True


def _context_values(field_name: str, context: TrackNormalizationContext) -> list[str]:
    if field_name == "genre":
        return _present(context.original_genre)
    if field_name == "artist":
        return _present(context.artist)
    if field_name == "title":
        return _present(context.title)
    if field_name == "album":
        return _present(context.album)
    if field_name == "file_name":
        return _present(context.file_name)
    if field_name == "keyword":
        return [
            value
            for value in (
                context.original_genre,
                context.artist,
                context.title,
                context.album,
                context.file_name,
            )
            if value
        ]
    raise ValueError(f"Unknown rule field: {field_name}")


def _present(value: str | None) -> list[str]:
    return [value] if value and value.strip() else []


def _match_candidates(value: str, *, split_genre: bool) -> set[str]:
    normalized = _normalize_text(value)
    candidates = {normalized}
    if split_genre:
        parts = [part.strip() for part in re.split(r"[/;,|]+", value) if part.strip()]
        candidates.update(_normalize_text(part) for part in parts)
    return candidates


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    normalized = normalized.lower().replace("&amp;", "&")
    normalized = normalized.replace("_", " ").replace("-", " ")
    normalized = re.sub(r"[()\[\]{}]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _best_genre_rule(rules: list[NormalizationRule]) -> NormalizationRule | None:
    if not rules:
        return None
    return max(rules, key=lambda rule: rule.confidence)


def _merge_tags(
    best: NormalizationRule | None, tag_matches: list[NormalizationRule]
) -> list[str]:
    tags: list[str] = []
    if best is not None:
        tags.extend(best.dj_use_tags)
    for rule in tag_matches:
        tags.extend(rule.dj_use_tags)
    return list(dict.fromkeys(tags))


def _has_any_context(context: TrackNormalizationContext) -> bool:
    return any(
        (
            context.original_genre,
            context.artist,
            context.title,
            context.album,
            context.file_name,
        )
    )
