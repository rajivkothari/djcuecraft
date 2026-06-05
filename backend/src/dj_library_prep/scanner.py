from __future__ import annotations

import os
from pathlib import Path

from dj_library_prep.models import SUPPORTED_EXTENSIONS


def scan_audio_files(folder: str | Path) -> list[Path]:
    root = Path(folder).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"Folder does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Expected a folder: {root}")

    audio_files = []
    for dirpath, _, filenames in os.walk(root, onerror=_ignore_walk_error):
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                audio_files.append(path)
    return sorted(audio_files)


def _ignore_walk_error(error: OSError) -> None:
    return None

