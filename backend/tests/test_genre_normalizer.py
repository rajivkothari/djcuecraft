from dj_library_prep.genre_normalizer import normalize_genre, suggest_track_metadata
from dj_library_prep.models import ReviewStatus


def test_mainstream_genre_mapping_is_high_confidence() -> None:
    result = normalize_genre("Hip-Hop/Rap")

    assert result.primary_genre == "Hip-Hop"
    assert result.confidence >= 0.9
    assert result.review_status == ReviewStatus.PENDING


def test_specific_latin_subgenre_mapping() -> None:
    result = normalize_genre("Salsa")

    assert result.primary_genre == "Latin"
    assert result.subgenre == "Salsa"
    assert result.review_status == ReviewStatus.PENDING


def test_specific_indian_subgenre_mapping() -> None:
    result = normalize_genre("Bhangra")

    assert result.primary_genre == "Indian"
    assert result.subgenre == "Punjabi-Bhangra"
    assert result.review_status == ReviewStatus.PENDING


def test_broad_tags_are_low_confidence_and_need_review() -> None:
    for genre in ("World", "Soundtrack", "International", "Indian", "Latin"):
        result = normalize_genre(genre)

        assert result.confidence < 0.5
        assert result.review_status == ReviewStatus.NEEDS_REVIEW


def test_broad_unknown_genre_preserves_low_confidence_rule() -> None:
    result = normalize_genre("World")

    assert result.primary_genre is None
    assert result.confidence == 0.25
    assert result.review_status == ReviewStatus.NEEDS_REVIEW


def test_missing_genre_needs_review() -> None:
    result = normalize_genre(None)

    assert result.primary_genre is None
    assert result.confidence == 0.0
    assert result.review_status == ReviewStatus.NEEDS_REVIEW


def test_latin_specific_rule_beats_broad_latin_rule() -> None:
    result = normalize_genre("Latin / Reggaeton")

    assert result.primary_genre == "Latin"
    assert result.subgenre == "Reggaeton"
    assert result.confidence == 0.82
    assert result.review_status == ReviewStatus.PENDING


def test_latin_keyword_rule_is_case_insensitive_and_needs_review() -> None:
    result = normalize_genre(None, title="Late Night DEMBOW Edit")

    assert result.primary_genre == "Latin"
    assert result.subgenre == "Dembow"
    assert result.review_status == ReviewStatus.NEEDS_REVIEW


def test_indian_filename_rule_marks_bollywood_as_needs_review() -> None:
    result = normalize_genre(None, file_name="bollywood_wedding_floorfiller.mp3")

    assert result.primary_genre == "Indian"
    assert result.subgenre == "Bollywood"
    assert "indian" in result.dj_use_tags
    assert result.review_status == ReviewStatus.NEEDS_REVIEW


def test_indian_keyword_rule_matches_desi_context() -> None:
    result = normalize_genre(None, title="Desi Club Mix")

    assert result.primary_genre == "Indian"
    assert "indian" in result.dj_use_tags
    assert result.confidence == 0.55


def test_artist_based_rule_can_propose_genre() -> None:
    result = normalize_genre(None, artist="Sean Paul")

    assert result.primary_genre == "Reggae-Dancehall"
    assert result.subgenre == "Dancehall"
    assert "dancehall" in result.dj_use_tags
    assert result.review_status == ReviewStatus.NEEDS_REVIEW


def test_dj_utility_rules_add_tags_without_replacing_genre() -> None:
    result = normalize_genre("Salsa", file_name="salsa_clean_intro.mp3")

    assert result.primary_genre == "Latin"
    assert result.subgenre == "Salsa"
    assert result.dj_use_tags == ["latin", "clean", "intro"]


def test_metadata_suggestion_returns_full_normalized_label_and_reason() -> None:
    result = suggest_track_metadata(
        original_genre="Hip-Hop/Rap",
        title="Club Rap Anthem",
        year="2004",
        file_name="club_rap_anthem.mp3",
    )

    assert result.to_dict() == {
        "suggested_decade": "00s",
        "suggested_genre": "Hip-Hop",
        "suggested_subgenre": "Club Rap",
        "normalized_label": "00s / Hip-Hop / Club Rap",
        "confidence": 0.93,
        "review_required": False,
        "reason": result.reason,
    }
    assert "Year tag indicates 2004" in result.reason
    assert "hip-hop patterns" in result.reason


def test_metadata_suggestion_broad_latin_requires_review() -> None:
    result = suggest_track_metadata(original_genre="Latin", year="1998")

    assert result.suggested_decade == "90s"
    assert result.suggested_genre == "Latin"
    assert result.suggested_subgenre is None
    assert result.normalized_label == "90s / Latin / Unknown"
    assert result.confidence < 0.7
    assert result.review_required is True


def test_metadata_suggestion_maps_bollywood_dance() -> None:
    result = suggest_track_metadata(
        original_genre="Bollywood",
        title="Wedding Dance Mix",
        year="2005",
    )

    assert result.suggested_decade == "00s"
    assert result.suggested_genre == "Bollywood"
    assert result.suggested_subgenre == "Dance"
    assert result.normalized_label == "00s / Bollywood / Dance"
    assert result.review_required is False


def test_metadata_suggestion_maps_reggaeton_with_accent() -> None:
    result = suggest_track_metadata(original_genre="Reggaetón", year="2017")

    assert result.normalized_label == "10s / Latin / Reggaeton"
    assert result.review_required is False


def test_metadata_suggestion_maps_freestyle_latin() -> None:
    result = suggest_track_metadata(
        original_genre="Freestyle",
        title="Latin Freestyle Classic",
        year="1992",
    )

    assert result.normalized_label == "90s / Freestyle / Latin Freestyle"
    assert result.review_required is False


def test_metadata_suggestion_missing_year_needs_review() -> None:
    result = suggest_track_metadata(original_genre="Salsa")

    assert result.normalized_label == "Unknown / Latin / Salsa"
    assert result.confidence < 0.7
    assert result.review_required is True


def test_metadata_suggestion_missing_year_always_needs_review() -> None:
    result = suggest_track_metadata(
        original_genre="Hip-Hop/Rap",
        title="Club Rap Anthem",
        file_name="club_rap_anthem_2004.mp3",
    )

    assert result.normalized_label == "Unknown / Hip-Hop / Club Rap"
    assert result.confidence < 0.7
    assert result.review_required is True


def test_metadata_suggestion_filename_only_specific_genre_needs_review() -> None:
    result = suggest_track_metadata(
        file_name="random_salsa_pool_edit_2004.mp3",
        year="2004",
    )

    assert result.normalized_label == "00s / Latin / Salsa"
    assert result.confidence < 0.7
    assert result.review_required is True


def test_metadata_suggestion_broad_genre_conflict_needs_review() -> None:
    result = suggest_track_metadata(
        original_genre="World",
        file_name="salsa_intro.mp3",
        year="1998",
    )

    assert result.normalized_label == "90s / Latin / Salsa"
    assert result.confidence < 0.7
    assert result.review_required is True


def test_metadata_suggestion_indian_regional_tags_alone_need_review() -> None:
    cases = [
        ("Hindi", "00s / Bollywood / Classic Bollywood"),
        ("Punjabi", "00s / Punjabi / Punjabi Pop"),
        ("Tamil", "00s / Tamil / Kollywood"),
    ]

    for original_genre, expected_label in cases:
        result = suggest_track_metadata(original_genre=original_genre, year="2005")

        assert result.normalized_label == expected_label
        assert result.confidence < 0.7
        assert result.review_required is True


def test_metadata_suggestion_dembow_title_does_not_become_confident_reggaeton() -> None:
    result = suggest_track_metadata(title="Late Night Dembow Edit", year="2019")

    assert result.normalized_label == "10s / Latin / Dembow"
    assert result.confidence < 0.7
    assert result.review_required is True


def test_metadata_suggestion_vague_dance_genre_needs_review() -> None:
    result = suggest_track_metadata(original_genre="Dance", year="2009")

    assert result.normalized_label == "00s / Unknown / Unknown"
    assert result.confidence < 0.7
    assert result.review_required is True
