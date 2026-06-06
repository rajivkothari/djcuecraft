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
    # Bollywood now maps to Indian (primary) with Bollywood Dance subgenre per spec change 5
    assert result.suggested_genre == "Indian"
    assert result.suggested_subgenre == "Bollywood Dance"
    assert result.normalized_label == "00s / Indian / Bollywood Dance"
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
    # Labels updated per session 6 spec:
    # - Hindi: language tag, not film industry -> Indian / Hindi (needs_review)
    # - Punjabi: broad tag -> Indian / Punjabi-Bhangra (needs_review, confidence 0.55)
    # - Tamil: regional tag -> Indian / Tamil (needs_review)
    cases = [
        ("Hindi", "00s / Indian / Hindi"),
        ("Punjabi", "00s / Indian / Punjabi-Bhangra"),
        ("Tamil", "00s / Indian / Tamil"),
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


# ---- New tests added in session 6 ----

def test_hindi_maps_to_indian_hindi_needs_review() -> None:
    # Hindi is a language, not a film industry — mapped with needs_review per spec
    result = suggest_track_metadata(original_genre="Hindi", year="2005")

    assert result.suggested_genre == "Indian"
    assert result.suggested_subgenre == "Hindi"
    assert result.review_required is True
    assert result.confidence < 0.7


def test_bollywood_with_dance_context_maps_to_bollywood_dance() -> None:
    result = suggest_track_metadata(
        original_genre="Bollywood",
        title="Club Dance Mix",
        year="2010",
    )

    assert result.suggested_genre == "Indian"
    assert result.suggested_subgenre == "Bollywood Dance"
    assert result.review_required is False


def test_bollywood_without_dance_context_maps_to_classic_bollywood() -> None:
    result = suggest_track_metadata(original_genre="Bollywood", year="2000")

    assert result.suggested_genre == "Indian"
    assert result.suggested_subgenre == "Classic Bollywood"
    assert result.review_required is False


def test_telugu_maps_to_indian_telugu_needs_review() -> None:
    result = normalize_genre("Telugu")

    assert result.primary_genre == "Indian"
    assert result.subgenre == "Telugu"
    assert result.review_status == ReviewStatus.NEEDS_REVIEW


def test_marathi_maps_to_indian_marathi_needs_review() -> None:
    result = normalize_genre("Marathi")

    assert result.primary_genre == "Indian"
    assert result.subgenre == "Marathi"
    assert result.review_status == ReviewStatus.NEEDS_REVIEW


def test_country_maps_to_country_genre() -> None:
    result = normalize_genre("Country")

    assert result.primary_genre == "Country"
    assert result.subgenre == "Country"
    assert result.review_status == ReviewStatus.PENDING


def test_house_maps_to_dance_house() -> None:
    result = normalize_genre("House")

    assert result.primary_genre == "Dance"
    assert result.subgenre == "House"
    assert result.review_status == ReviewStatus.PENDING


def test_edm_maps_to_dance_edm() -> None:
    result = normalize_genre("EDM")

    assert result.primary_genre == "Dance"
    assert result.subgenre == "EDM"
    assert result.review_status == ReviewStatus.PENDING


def test_trap_maps_to_hip_hop_trap() -> None:
    result = normalize_genre("Trap Music")

    assert result.primary_genre == "Hip-Hop"
    assert result.subgenre == "Trap"
    assert result.review_status == ReviewStatus.PENDING


def test_pop_with_dance_context_maps_to_dance_pop() -> None:
    result = suggest_track_metadata(
        original_genre="Pop",
        title="Club Remix Edit",
        year="2015",
    )

    assert result.suggested_genre == "Pop"
    assert result.suggested_subgenre == "Dance Pop"
    assert result.review_required is False


def test_freestyle_with_latin_context_maps_to_latin_freestyle() -> None:
    result = suggest_track_metadata(
        original_genre="Freestyle",
        title="Latin Night Mix",
        year="1995",
    )

    assert result.suggested_genre == "Freestyle"
    assert result.suggested_subgenre == "Latin Freestyle"
    assert result.review_required is False


def test_merengue_maps_to_latin_merengue() -> None:
    result = normalize_genre("Merengue")

    assert result.primary_genre == "Latin"
    assert result.subgenre == "Merengue"
    assert result.review_status == ReviewStatus.PENDING


def test_punjabi_maps_with_needs_review() -> None:
    # Punjabi is a broad language tag — could be bhangra, pop, or folk
    result = suggest_track_metadata(original_genre="Punjabi", year="2010")

    assert result.suggested_genre == "Indian"
    assert result.review_required is True
    assert result.confidence < 0.7


def test_normalize_genre_and_suggest_track_metadata_produce_consistent_results() -> None:
    # After consolidation both use the same code path
    genre = "Salsa"
    year = "1998"

    norm = normalize_genre(genre)
    suggestion = suggest_track_metadata(original_genre=genre, year=year)

    assert norm.primary_genre == suggestion.suggested_genre
    assert norm.subgenre == suggestion.suggested_subgenre


# ---- Part A: word_boundary false positive fix tests (session 7) ----

def test_word_boundary_edit_in_filename_gets_edit_tag() -> None:
    result = normalize_genre("Salsa", file_name="salsa_club_edit.mp3")

    assert "edit" in result.dj_use_tags


def test_word_boundary_unedited_does_not_get_edit_tag() -> None:
    result = normalize_genre(None, title="Unedited Version")

    assert "edit" not in result.dj_use_tags
    assert "remix-edit" not in result.dj_use_tags


def test_word_boundary_editors_cut_does_not_get_edit_tag() -> None:
    result = normalize_genre(None, title="Editor's Cut")

    assert "edit" not in result.dj_use_tags


def test_word_boundary_parenthetical_radio_edit_gets_edit_tag() -> None:
    result = normalize_genre(None, title="Song (Radio Edit)")

    assert "edit" in result.dj_use_tags


def test_word_boundary_bracket_intro_gets_intro_tag() -> None:
    result = normalize_genre(None, title="Song [Intro]")

    assert "intro" in result.dj_use_tags


def test_word_boundary_introduction_does_not_get_intro_tag() -> None:
    result = normalize_genre(None, title="Introduction to Jazz")

    assert "intro" not in result.dj_use_tags


def test_word_boundary_introducing_does_not_get_intro_tag() -> None:
    result = normalize_genre(None, title="Introducing the Band")

    assert "intro" not in result.dj_use_tags


def test_word_boundary_salsa_clean_intro_file_still_gets_clean_and_intro() -> None:
    # Regression: this case worked before and must continue to work
    result = normalize_genre("Salsa", file_name="salsa_clean_intro.mp3")

    assert result.primary_genre == "Latin"
    assert result.subgenre == "Salsa"
    assert "clean" in result.dj_use_tags
    assert "intro" in result.dj_use_tags


def test_word_boundary_remix_in_title_gets_remix_edit_tag() -> None:
    result = normalize_genre(None, title="Song (Remix)")

    assert "remix-edit" in result.dj_use_tags


def test_word_boundary_remix_in_genre_tag_still_matches() -> None:
    result = normalize_genre("Remix")

    assert "remix-edit" in result.dj_use_tags
