from __future__ import annotations

import json
import os
import re
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
        escaped = False
        for char in body:
            if quote:
                current += char
                if quote == '"' and char == "\\" and not escaped:
                    escaped = True
                    continue
                if char == quote and not escaped:
                    quote = ""
                escaped = False
            elif char in {"'", '"'}:
                quote = char
                current += char
            elif char == ",":
                items.append(parse_toml_scalar(current))
                current = ""
            else:
                current += char
        if quote:
            raise ValueError("unterminated quoted TOML array item")
        if current.strip():
            items.append(parse_toml_scalar(current))
        return items
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid quoted TOML string: {exc}") from exc
        if not isinstance(parsed, str):
            raise ValueError("TOML value must be a string")
        return parsed
    if len(value) >= 2 and value[0] == value[-1] == "'":
        if "'" in value[1:-1]:
            raise ValueError("invalid literal TOML string")
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    if re.fullmatch(r"[-+]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][-+]?\d+)?", value):
        return float(value)
    raise ValueError(f"unsupported or malformed TOML value: {value!r}")


def _without_toml_comment(source: str) -> str:
    quote = ""
    escaped = False
    for index, char in enumerate(source):
        if quote:
            if quote == '"' and char == "\\" and not escaped:
                escaped = True
                continue
            if char == quote and not escaped:
                quote = ""
            escaped = False
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == "#":
            return source[:index]
    if quote:
        raise ValueError("unterminated quoted TOML string")
    return source


def parse_simple_toml(text: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    current: dict[str, Any] = payload
    explicit_tables: set[tuple[str, ...]] = set()
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = _without_toml_comment(raw).strip()
        if not line:
            continue
        table_match = re.fullmatch(
            r"\[([A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*)\]",
            line,
        )
        if table_match:
            parts = tuple(table_match.group(1).split("."))
            if parts in explicit_tables:
                raise ValueError(f"duplicate TOML table at line {line_number}")
            explicit_tables.add(parts)
            current = payload
            for key in parts:
                nested = current.setdefault(key, {})
                if not isinstance(nested, dict):
                    raise ValueError(
                        f"TOML table conflicts with a value at line {line_number}"
                    )
                current = nested
            continue
        if line.startswith("["):
            raise ValueError(f"malformed TOML table at line {line_number}")
        if "=" not in line:
            raise ValueError(f"malformed TOML assignment at line {line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
            raise ValueError(f"invalid TOML key at line {line_number}")
        if key in current:
            raise ValueError(f"duplicate TOML key {key!r} at line {line_number}")
        current[key] = parse_toml_scalar(value)
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
