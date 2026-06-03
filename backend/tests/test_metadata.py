from pathlib import Path

from dj_library_prep import metadata
from dj_library_prep.models import ReviewStatus


def test_read_track_metadata_handles_unparseable_audio(monkeypatch) -> None:
    def broken_mutagen_file(path: Path, easy: bool) -> object:
        raise RuntimeError("unparseable")

    monkeypatch.setattr(metadata, "MutagenFile", broken_mutagen_file)

    track = metadata.read_track_metadata("bad.mp3")

    assert track.file_name == "bad.mp3"
    assert track.metadata_confidence == 0.0
    assert track.review_status == ReviewStatus.NEEDS_REVIEW

