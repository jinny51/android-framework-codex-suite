from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact_paths import require_safe_artifact_path


def write_json(path: Path, payload: Any, *, sort_keys: bool = True) -> None:
    path = require_safe_artifact_path(path, purpose="JSON output")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=sort_keys) + "\n",
        encoding="utf-8",
    )
