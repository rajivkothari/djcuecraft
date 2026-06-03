import pytest

from dj_library_prep.models import ReviewStatus, Track, normalize_decade


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (1979, "70s"),
        ("1984", "80s"),
        ("1999-01-01", "90s"),
        ("2008", "00s"),
        ("2017", "10s"),
        ("2024", "20s"),
        (None, "Unknown"),
        ("", "Unknown"),
        ("1969", "Unknown"),
        ("not a year", "Unknown"),
    ],
)
def test_normalize_decade(year: object, expected: str) -> None:
    assert normalize_decade(year) == expected


def test_track_rejects_unsupported_extension() -> None:
    with pytest.raises(ValueError):
        Track(file_path="track.aiff", file_name="track.aiff", file_extension=".aiff")


def test_track_reports_missing_metadata_fields() -> None:
    track = Track(
        file_path="song.mp3",
        file_name="song.mp3",
        file_extension=".mp3",
        artist="Artist",
        review_status=ReviewStatus.NEEDS_REVIEW,
    )

    assert track.missing_fields() == ["title", "year", "original_genre"]

