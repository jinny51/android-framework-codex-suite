from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def default_codex_home() -> str:
    return os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")


def expand_codex_path(value: str | os.PathLike[str], *, resolve: bool = False) -> Path:
    codex_home = default_codex_home()
    text = str(value).replace("${CODEX_HOME}", codex_home).replace("$CODEX_HOME", codex_home)
    path = Path(os.path.expandvars(os.path.expanduser(text)))
    return path.resolve() if resolve else path


def parse_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_toml_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        if not body:
            return []
        items: list[Any] = []
        current = ""
        quote = ""
        for char in body:
            if quote:
                current += char
                if char == quote:
                    quote = ""
            elif char in {"'", '"'}:
                quote = char
                current += char
            elif char == ",":
                items.append(parse_toml_scalar(current))
                current = ""
            else:
                current += char
        if current.strip():
            items.append(parse_toml_scalar(current))
        return items
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    return value


def parse_simple_toml(text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    current: dict[str, Any] = payload
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = payload
            for part in line[1:-1].split("."):
                key = part.strip().strip('"').strip("'")
                nested = current.setdefault(key, {})
                if not isinstance(nested, dict):
                    nested = {}
                    current[key] = nested
                current = nested
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        current[key.strip()] = parse_toml_scalar(value)
    return payload


def load_toml(path: Path, *, strict: bool = False) -> dict[str, Any]:
    try:
        try:
            import tomllib  # type: ignore[attr-defined]

            with path.open("rb") as handle:
                return tomllib.load(handle)
        except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
            return parse_simple_toml(path.read_text(encoding="utf-8"))
    except Exception as exc:
        if strict:
            raise ValueError(str(exc)) from exc
        return {}


def find_project_report_config(start: Path | None = None) -> Path | None:
    try:
        current = (start or Path.cwd()).resolve()
    except OSError:
        return None
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / ".codex" / "report.toml"
        if candidate.exists():
            return candidate
    return None
