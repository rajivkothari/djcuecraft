from dj_library_prep.genre_normalizer import normalize_genre
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
