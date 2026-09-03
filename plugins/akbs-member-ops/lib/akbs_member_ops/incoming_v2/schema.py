"""Dependency-free validator for the strict Draft 2020-12 subset used by AKBS v2."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


class SchemaError(ValueError):
    """A JSON document or schema-subset assertion is invalid."""


DRAFT_2020_12_SCHEMA = "https://json-schema.org/draft/2020-12/schema"
_SUPPORTED_SCHEMA_KEYWORDS = {
    "$defs",
    "$id",
    "$ref",
    "$schema",
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "contains",
    "description",
    "else",
    "enum",
    "format",
    "if",
    "items",
    "maxItems",
    "maxLength",
    "maxProperties",
    "maximum",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
    "not",
    "oneOf",
    "pattern",
    "properties",
    "propertyNames",
    "required",
    "then",
    "title",
    "type",
    "unevaluatedProperties",
    "uniqueItems",
}
_SCHEMA_TYPES = {"array", "boolean", "integer", "null", "number", "object", "string"}


def load_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise SchemaError(f"duplicate JSON key: {label}: {key}")
            value[key] = item
        return value

    def reject_constant(value: str) -> None:
        raise SchemaError(f"non-finite JSON number: {label}: {value}")

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=strict_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaError(f"strict JSON parse failed: {label}") from exc
    if not isinstance(value, dict):
        raise SchemaError(f"JSON document must be an object: {label}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        return load_json_bytes(path.read_bytes(), label=str(path))
    except OSError as exc:
        raise SchemaError(f"cannot read JSON document: {path}: {exc}") from exc


def _resolve_ref(root: Mapping[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        raise SchemaError(f"non-local JSON Schema ref: {reference}")
    value: Any = root
    for raw in reference[2:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, Mapping) or token not in value:
            raise SchemaError(f"unresolved JSON Schema ref: {reference}")
        value = value[token]
    return value


def _require_string_array(value: Any, *, keyword: str, path: str) -> None:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) for item in value)
        or len(value) != len(set(value))
    ):
        raise SchemaError(f"invalid {keyword} in schema at {path}")


def _validate_schema_node(schema: Any, root: Mapping[str, Any], path: str) -> None:
    """Fail closed when a bundled schema uses syntax this validator cannot enforce."""
    if isinstance(schema, bool):
        return
    if not isinstance(schema, Mapping):
        raise SchemaError(f"schema is not an object at {path}")
    unsupported = set(schema) - _SUPPORTED_SCHEMA_KEYWORDS
    if unsupported:
        raise SchemaError(
            f"unsupported Draft 2020-12 schema keywords at {path}: "
            + ", ".join(sorted(unsupported))
        )
    for keyword in ("$id", "$ref", "$schema", "description", "title"):
        if keyword in schema and not isinstance(schema[keyword], str):
            raise SchemaError(f"invalid {keyword} in schema at {path}")
    if "$ref" in schema:
        _resolve_ref(root, schema["$ref"])
    if "type" in schema:
        declared = [schema["type"]] if isinstance(schema["type"], str) else schema["type"]
        if (
            not isinstance(declared, list)
            or not declared
            or any(item not in _SCHEMA_TYPES for item in declared)
            or len(declared) != len(set(declared))
        ):
            raise SchemaError(f"invalid type in schema at {path}")
    if "required" in schema:
        _require_string_array(schema["required"], keyword="required", path=path)
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise SchemaError(f"invalid enum in schema at {path}")
    for keyword in ("minItems", "maxItems", "minLength", "maxLength", "minProperties", "maxProperties"):
        if keyword in schema and (
            not isinstance(schema[keyword], int)
            or isinstance(schema[keyword], bool)
            or schema[keyword] < 0
        ):
            raise SchemaError(f"invalid {keyword} in schema at {path}")
    for keyword in ("minimum", "maximum"):
        if keyword in schema and (
            not isinstance(schema[keyword], (int, float))
            or isinstance(schema[keyword], bool)
            or not math.isfinite(schema[keyword])
        ):
            raise SchemaError(f"invalid {keyword} in schema at {path}")
    if "pattern" in schema:
        if not isinstance(schema["pattern"], str):
            raise SchemaError(f"invalid pattern in schema at {path}")
        try:
            re.compile(schema["pattern"])
        except re.error as exc:
            raise SchemaError(f"invalid pattern in schema at {path}") from exc
    if "format" in schema and schema["format"] != "date-time":
        raise SchemaError(f"unsupported format in schema at {path}: {schema['format']!r}")
    for keyword in ("uniqueItems", "unevaluatedProperties"):
        if keyword in schema and not isinstance(schema[keyword], bool):
            raise SchemaError(f"invalid {keyword} in schema at {path}")
    if "additionalProperties" in schema and not isinstance(
        schema["additionalProperties"], (bool, Mapping)
    ):
        raise SchemaError(f"invalid additionalProperties in schema at {path}")
    for keyword in ("properties", "$defs"):
        children = schema.get(keyword)
        if children is None:
            continue
        if not isinstance(children, Mapping) or any(not isinstance(name, str) for name in children):
            raise SchemaError(f"invalid {keyword} in schema at {path}")
        for name, child in children.items():
            _validate_schema_node(child, root, f"{path}/{keyword}/{name}")
    for keyword in (
        "additionalProperties",
        "contains",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
    ):
        child = schema.get(keyword)
        if child is not None and keyword != "additionalProperties":
            _validate_schema_node(child, root, f"{path}/{keyword}")
        elif isinstance(child, Mapping):
            _validate_schema_node(child, root, f"{path}/{keyword}")
    for keyword in ("allOf", "anyOf", "oneOf"):
        children = schema.get(keyword)
        if children is None:
            continue
        if not isinstance(children, list) or not children:
            raise SchemaError(f"invalid {keyword} in schema at {path}")
        for index, child in enumerate(children):
            _validate_schema_node(child, root, f"{path}/{keyword}/{index}")


def validate_draft_2020_12_schema(schema: dict[str, Any]) -> None:
    """Validate the declared dialect and every enforceable schema keyword first."""
    if schema.get("$schema") != DRAFT_2020_12_SCHEMA:
        raise SchemaError("schema does not declare Draft 2020-12")
    _validate_schema_node(schema, schema, "$")


def _type_matches(value: Any, expected: str) -> bool:
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and float(value).is_integer()
        ),
        "number": (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        ),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    if expected not in matches:
        raise SchemaError(f"unsupported JSON Schema type: {expected}")
    return matches[expected]


def _json_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    if (
        isinstance(left, (int, float))
        and not isinstance(left, bool)
        and isinstance(right, (int, float))
        and not isinstance(right, bool)
    ):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(
            _json_equal(item, right[index]) for index, item in enumerate(left)
        )
    if isinstance(left, dict):
        return set(left) == set(right) and all(_json_equal(left[key], right[key]) for key in left)
    return left == right


def _is_valid(value: Any, schema: Any, root: Mapping[str, Any]) -> bool:
    try:
        validate(value, schema, root)
        return True
    except SchemaError:
        return False


def validate(value: Any, schema: Any, root: Mapping[str, Any], path: str = "$") -> None:
    """Validate one value using only keywords present in the bundled contracts."""
    if schema is False:
        raise SchemaError(f"false schema at {path}")
    if schema is True:
        return
    if not isinstance(schema, Mapping):
        raise SchemaError(f"schema is not an object at {path}")
    if "$ref" in schema:
        validate(value, _resolve_ref(root, str(schema["$ref"])), root, path)
    if "type" in schema:
        expected = [schema["type"]] if isinstance(schema["type"], str) else schema["type"]
        if not isinstance(expected, list) or not any(_type_matches(value, item) for item in expected):
            raise SchemaError(f"type mismatch at {path}")
    if "const" in schema and not _json_equal(value, schema["const"]):
        raise SchemaError(f"const mismatch at {path}")
    if "enum" in schema and not any(_json_equal(value, item) for item in schema["enum"]):
        raise SchemaError(f"enum mismatch at {path}")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            raise SchemaError(f"minLength at {path}")
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            raise SchemaError(f"maxLength at {path}")
        if "pattern" in schema and re.search(str(schema["pattern"]), value) is None:
            raise SchemaError(f"pattern mismatch at {path}")
        if schema.get("format") == "date-time":
            match = re.fullmatch(
                r"(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})[Tt]"
                r"(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
                r"(?:\.(?P<fraction>[0-9]+))?"
                r"(?P<zone>[Zz]|(?P<sign>[+-])(?P<offset_hour>[0-9]{2}):(?P<offset_minute>[0-9]{2}))",
                value,
            )
            if match is None:
                raise SchemaError(f"date-time mismatch at {path}")
            try:
                datetime(int(match["year"]), int(match["month"]), int(match["day"]))
            except ValueError as exc:
                raise SchemaError(f"date-time mismatch at {path}") from exc
            if (
                int(match["hour"]) > 23
                or int(match["minute"]) > 59
                or int(match["second"]) > 60
                or (
                    match["zone"] not in {"Z", "z"}
                    and (int(match["offset_hour"]) > 23 or int(match["offset_minute"]) > 59)
                )
            ):
                raise SchemaError(f"date-time mismatch at {path}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise SchemaError(f"non-finite number at {path}")
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaError(f"minimum at {path}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaError(f"maximum at {path}")
    if isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            raise SchemaError(f"minItems at {path}")
        if "maxItems" in schema and len(value) > int(schema["maxItems"]):
            raise SchemaError(f"maxItems at {path}")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in value]
            if len(encoded) != len(set(encoded)):
                raise SchemaError(f"uniqueItems at {path}")
        if "items" in schema:
            for index, item in enumerate(value):
                validate(item, schema["items"], root, f"{path}/{index}")
        if "contains" in schema and not any(_is_valid(item, schema["contains"], root) for item in value):
            raise SchemaError(f"contains at {path}")
    if isinstance(value, dict):
        required = set(schema.get("required") or [])
        if not required.issubset(value):
            missing = ", ".join(sorted(required - set(value)))
            raise SchemaError(f"required missing at {path}: {missing}")
        properties = schema.get("properties") or {}
        for name, child in properties.items():
            if name in value:
                validate(value[name], child, root, f"{path}/{name}")
        if "propertyNames" in schema:
            for name in value:
                validate(name, schema["propertyNames"], root, f"{path}/<name>")
        unknown = set(value) - set(properties)
        additional = schema.get("additionalProperties", True)
        if additional is False and unknown:
            raise SchemaError(f"additional properties at {path}: {', '.join(sorted(unknown))}")
        if isinstance(additional, Mapping):
            for name in unknown:
                validate(value[name], additional, root, f"{path}/{name}")
        if schema.get("unevaluatedProperties") is False and unknown:
            raise SchemaError(f"unevaluated properties at {path}: {', '.join(sorted(unknown))}")
        if len(value) < int(schema.get("minProperties", 0)):
            raise SchemaError(f"minProperties at {path}")
        if "maxProperties" in schema and len(value) > int(schema["maxProperties"]):
            raise SchemaError(f"maxProperties at {path}")
    for child in schema.get("allOf") or []:
        validate(value, child, root, path)
    if "anyOf" in schema and not any(_is_valid(value, child, root) for child in schema["anyOf"]):
        raise SchemaError(f"anyOf at {path}")
    if "oneOf" in schema and sum(_is_valid(value, child, root) for child in schema["oneOf"]) != 1:
        raise SchemaError(f"oneOf at {path}")
    if "not" in schema and _is_valid(value, schema["not"], root):
        raise SchemaError(f"not at {path}")
    if "if" in schema:
        branch = schema.get("then") if _is_valid(value, schema["if"], root) else schema.get("else")
        if branch is not None:
            validate(value, branch, root, path)


def validate_document(document: dict[str, Any], schema: dict[str, Any]) -> None:
    validate_draft_2020_12_schema(schema)
    validate(document, schema, schema)
