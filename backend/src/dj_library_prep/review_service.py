from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dj_library_prep import database
from dj_library_prep.genre_normalizer import suggest_track_metadata
from dj_library_prep.models import ReviewStatus


EDITABLE_FIELDS = {
    "normalized_decade",
    "normalized_primary_genre",
    "normalized_subgenre",
    "dj_use_tags",
    "review_status",
}


def list_review_tracks(
    database_path: str | Path = "djcuecraft.sqlite3",
    review_status: str | None = None,
) -> list[dict[str, Any]]:
    with database.connect(database_path) as connection:
        rows = database.list_tracks(connection)

    tracks = [_track_payload(row) for row in rows]
    if review_status:
        tracks = [track for track in tracks if track["review_status"] == review_status]
    return tracks


def update_review_track(
    track_id: int,
    updates: dict[str, Any],
    database_path: str | Path = "djcuecraft.sqlite3",
) -> dict[str, Any]:
    unsupported = sorted(set(updates).difference(EDITABLE_FIELDS))
    if unsupported:
        raise ValueError(f"Unsupported review update fields: {', '.join(unsupported)}")

    with database.connect(database_path) as connection:
        current = database.get_track_by_id(connection, track_id)
        if current is None:
            raise KeyError(f"Track not found: {track_id}")

        normalized_decade = str(
            updates.get("normalized_decade", current["normalized_decade"]) or "Unknown"
        )
        normalized_primary = _blank_to_none(
            updates.get("normalized_primary_genre", current["normalized_primary_genre"])
        )
        normalized_subgenre = _blank_to_none(
            updates.get("normalized_subgenre", current["normalized_subgenre"])
        )
        dj_use_tags = _tags_to_json(updates.get("dj_use_tags", current["dj_use_tags"]))
        review_status = _review_status(
            updates.get("review_status", current["review_status"])
        )

        if _pending_values_match(
            current,
            normalized_decade,
            normalized_primary,
            normalized_subgenre,
            dj_use_tags,
            review_status.value,
        ):
            return _track_payload(current)

        updated = database.update_track_review_fields(
            connection=connection,
            track_id=track_id,
            normalized_decade=normalized_decade,
            normalized_primary_genre=normalized_primary,
            normalized_subgenre=normalized_subgenre,
            dj_use_tags=dj_use_tags,
            review_status=review_status.value,
        )
        if updated is not None:
            database.record_review_history(
                connection,
                current,
                updated,
                source="user_edit",
                action=_audit_action(current, updated, review_status),
                reason=_audit_reason(current, updated, review_status),
            )
        connection.commit()

    if updated is None:
        raise KeyError(f"Track not found after update: {track_id}")
    return _track_payload(updated)


def list_review_history(
    track_id: int,
    database_path: str | Path = "djcuecraft.sqlite3",
) -> list[dict[str, Any]]:
    with database.connect(database_path) as connection:
        rows = database.list_review_history_by_track_id(connection, track_id)
    return [dict(row) for row in rows]


def _track_payload(row: Any) -> dict[str, Any]:
    values = dict(row)
    values["dj_use_tags"] = _format_tags(values.get("dj_use_tags"))
    values["missing_fields"] = [
        field_name
        for field_name in ("artist", "title", "year", "original_genre")
        if not values.get(field_name)
    ]
    suggestion = suggest_track_metadata(
        original_genre=values.get("original_genre"),
        artist=values.get("artist"),
        title=values.get("title"),
        album=values.get("album"),
        year=values.get("year"),
        file_name=values.get("file_name"),
    )
    values["suggested_decade"] = values.get("normalized_decade")
    values["suggested_genre"] = values.get("normalized_primary_genre")
    values["suggested_subgenre"] = values.get("normalized_subgenre")
    values["suggested_normalized_label"] = _normalized_label(
        values.get("normalized_decade"),
        values.get("normalized_primary_genre"),
        values.get("normalized_subgenre"),
    )
    values["review_required"] = (
        suggestion.review_required
        or values["review_status"] == ReviewStatus.NEEDS_REVIEW.value
    )
    values["reason"] = suggestion.reason
    return values


def _review_status(value: Any) -> ReviewStatus:
    return ReviewStatus(str(value or ReviewStatus.NEEDS_REVIEW.value))


def _audit_action(current: Any, updated: Any, review_status: ReviewStatus) -> str:
    if _normalized_values_changed(current, updated):
        return "edit"
    return {
        ReviewStatus.APPROVED: "approve",
        ReviewStatus.EDITED: "edit",
        ReviewStatus.REJECTED: "reject",
        ReviewStatus.SKIPPED: "skip",
    }.get(review_status, "edit")


def _audit_reason(current: Any, updated: Any, review_status: ReviewStatus) -> str:
    if _normalized_values_changed(current, updated):
        return "User edited the normalized metadata."
    return {
        ReviewStatus.APPROVED: "User approved the metadata suggestion.",
        ReviewStatus.EDITED: "User edited the normalized metadata.",
        ReviewStatus.REJECTED: "User rejected the metadata suggestion.",
        ReviewStatus.SKIPPED: "User skipped the track during review.",
    }.get(review_status, "User updated the review decision.")


def _normalized_values_changed(current: Any, updated: Any) -> bool:
    tracked_fields = (
        "normalized_decade",
        "normalized_primary_genre",
        "normalized_subgenre",
        "dj_use_tags",
    )
    return any(_compare(current[field]) != _compare(updated[field]) for field in tracked_fields)


def _blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_tags(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, list):
        return ";".join(str(tag) for tag in value)
    if not isinstance(value, str):
        return str(value)
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(decoded, list):
        return ";".join(str(tag) for tag in decoded)
    return str(decoded)


def _tags_to_json(value: Any) -> str:
    if value is None:
        return "[]"
    if isinstance(value, list):
        return json.dumps([str(tag).strip() for tag in value if str(tag).strip()])

    text = str(value).strip()
    if not text:
        return "[]"
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        decoded = [tag.strip() for tag in text.split(";") if tag.strip()]
    if isinstance(decoded, list):
        return json.dumps([str(tag).strip() for tag in decoded if str(tag).strip()])
    return json.dumps([str(decoded).strip()])


def _pending_values_match(
    current: Any,
    normalized_decade: str,
    normalized_primary: str | None,
    normalized_subgenre: str | None,
    dj_use_tags: str,
    review_status: str,
) -> bool:
    return (
        _compare(current["normalized_decade"]) == _compare(normalized_decade)
        and _compare(current["normalized_primary_genre"]) == _compare(normalized_primary)
        and _compare(current["normalized_subgenre"]) == _compare(normalized_subgenre)
        and _compare(current["dj_use_tags"]) == _compare(dj_use_tags)
        and _compare(current["review_status"]) == _compare(review_status)
    )


def _compare(value: Any) -> str:
    return "" if value is None else str(value)


def _normalized_label(
    decade: Any,
    primary_genre: Any,
    subgenre: Any,
) -> str:
    return " / ".join(
        [
            str(decade or "Unknown"),
            str(primary_genre or "Unknown"),
            str(subgenre or "Unknown"),
        ]
    )
