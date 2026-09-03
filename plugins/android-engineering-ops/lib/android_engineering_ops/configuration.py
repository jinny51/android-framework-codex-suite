"""Dependency-free parser for the frozen Android engineering user config."""

from __future__ import annotations

import re


class EngineeringConfigError(ValueError):
    """The public engineering configuration is outside its frozen subset."""


_ASSIGNMENT = re.compile(
    r'^([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*"([^"\\\x00-\x1f]*)"\s*$'
)


def parse_engineering_config(
    raw: bytes,
    *,
    allow_identity: bool,
    require_extension: bool,
) -> dict[str, dict[str, str]]:
    """Parse only unique tables containing unique quoted-string assignments.

    Project configuration is extension-only.  The user-level
    ``android-engineering-ops.toml`` may additionally carry the standalone
    attribution identity, but no project file may supply that identity.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EngineeringConfigError("engineering config must be strict UTF-8") from exc
    if text.startswith("\ufeff"):
        raise EngineeringConfigError("engineering config must not contain a UTF-8 BOM")

    allowed_tables = {"extension", *( ["identity"] if allow_identity else [])}
    result: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line_number, source_line in enumerate(text.splitlines(), start=1):
        line = source_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            if not line.endswith("]") or line.count("[") != 1 or line.count("]") != 1:
                raise EngineeringConfigError(
                    f"engineering config has a malformed table at line {line_number}"
                )
            table = line[1:-1]
            if table not in allowed_tables:
                raise EngineeringConfigError(
                    f"engineering config contains unsupported table [{table}]"
                )
            if table in result:
                raise EngineeringConfigError(
                    f"engineering config repeats [{table}]"
                )
            current = {}
            result[table] = current
            continue
        if current is None:
            raise EngineeringConfigError(
                f"engineering config value precedes a table at line {line_number}"
            )
        match = _ASSIGNMENT.fullmatch(line)
        if match is None:
            raise EngineeringConfigError(
                "engineering config accepts only key = \"string\" assignments; "
                f"invalid line {line_number}"
            )
        key, value = match.groups()
        if key in current:
            raise EngineeringConfigError(f"engineering config repeats key: {key}")
        current[key] = value

    if require_extension and "extension" not in result:
        raise EngineeringConfigError(
            "project engineering config must contain exactly one [extension]"
        )
    if not result:
        raise EngineeringConfigError("engineering config contains no supported table")
    if "identity" in result and set(result["identity"]) != {"member_alias"}:
        raise EngineeringConfigError(
            "[identity] requires exactly the member_alias string"
        )
    return result
