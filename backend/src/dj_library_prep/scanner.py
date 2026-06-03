from __future__ import annotations

from pathlib import Path
from collections.abc import Iterable

from dj_library_prep.models import SUPPORTED_EXTENSIONS


def scan_audio_files(folder: str | Path) -> list[Path]:
    root = Path(folder).expanduser()
    if not root.exists():
        raise FileNotFoundError(f"Folder does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Expected a folder: {root}")

    files: Iterable[Path] = root.rglob("*")
    return sorted(
        path for path in files if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )

