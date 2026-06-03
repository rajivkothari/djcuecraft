from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
import json
import re
from typing import Any

from dj_library_prep.models import ReviewStatus, normalize_decade


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


@dataclass(frozen=True, slots=True)
class TrackNormalizationContext:
    original_genre: str | None = None
    artist: str | None = None
    title: str | None = None
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

    review_status = best.review_status
    if any(rule.review_status == ReviewStatus.NEEDS_REVIEW for rule in tag_matches):
        review_status = ReviewStatus.NEEDS_REVIEW

    return GenreNormalization(
        primary_genre=best.primary_genre,
        subgenre=best.subgenre,
        dj_use_tags=tags,
        confidence=best.confidence,
        review_status=review_status,
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
    )


def _rule_matches(rule: NormalizationRule, context: TrackNormalizationContext) -> bool:
    values = _context_values(rule.field_name, context)
    if not values:
        return False

    for value in values:
        candidates = _match_candidates(value, split_genre=rule.field_name == "genre")
        for rule_value in rule.values:
            normalized_rule_value = _normalize_text(rule_value)
            if rule.match_type == "exact" and normalized_rule_value in candidates:
                return True
            if rule.match_type == "contains" and any(
                normalized_rule_value in candidate for candidate in candidates
            ):
                return True
    return False


def _context_values(field_name: str, context: TrackNormalizationContext) -> list[str]:
    if field_name == "genre":
        return _present(context.original_genre)
    if field_name == "artist":
        return _present(context.artist)
    if field_name == "title":
        return _present(context.title)
    if field_name == "file_name":
        return _present(context.file_name)
    if field_name == "keyword":
        return [
            value
            for value in (
                context.original_genre,
                context.artist,
                context.title,
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
    normalized = value.lower().replace("&amp;", "&")
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
    return any((context.original_genre, context.artist, context.title, context.file_name))
