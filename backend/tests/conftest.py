from __future__ import annotations

from pathlib import Path
import re
import uuid

import pytest


@pytest.fixture
def tmp_path(request) -> Path:
    root = Path.cwd() / ".test-tmp"
    root.mkdir(exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name)
    path = root / f"{safe_name}-{uuid.uuid4().hex}"
    path.mkdir()
    return path
