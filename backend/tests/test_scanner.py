from dj_library_prep import scanner


def test_scan_audio_files_skips_unsupported_files(tmp_path) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    mp3_path = music_dir / "song.mp3"
    txt_path = music_dir / "notes.txt"
    mp3_path.write_bytes(b"audio")
    txt_path.write_text("not audio", encoding="utf-8")

    assert scanner.scan_audio_files(music_dir) == [mp3_path]


def test_scan_audio_files_ignores_folder_walk_errors(tmp_path, monkeypatch) -> None:
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    mp3_path = music_dir / "song.mp3"

    def walk_with_error(root, onerror):
        onerror(OSError("cannot read folder"))
        yield root, [], ["song.mp3", "notes.txt"]

    monkeypatch.setattr(scanner.os, "walk", walk_with_error)

    assert scanner.scan_audio_files(music_dir) == [mp3_path]
