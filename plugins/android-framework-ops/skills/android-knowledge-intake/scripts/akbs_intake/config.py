from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
OPS_PLUGIN_LIB = Path(__file__).resolve().parents[4] / "lib"
if OPS_PLUGIN_LIB.is_dir() and str(OPS_PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(OPS_PLUGIN_LIB))

from android_framework_ops.artifact_paths import artifact_path_guard_error, require_safe_artifact_path

INCOMING_SCHEMA_VERSION = "1"
ENV_PREFIXES = ("CODEX_REPORT_", "CODEX_WORK_REPORT_")
DEFAULT_SUBMISSION_API_BASE_URL = "http://192.168.100.118:8088/akbs/api"
DEFAULT_SUBMISSION_SESSION_COOKIE = ""
DEFAULT_SUBMISSION_API_TOKEN = ""
DEFAULT_KNOWLEDGE_REPO_URL = ""
AKBS_ENDPOINT_ENV_PREFIXES = ("CODEX_REPORT_AKBS_ENDPOINT_", "CODEX_WORK_REPORT_AKBS_ENDPOINT_")
AKBS_ENDPOINT_DEFAULTS = {
    "submission_api_base_url": DEFAULT_SUBMISSION_API_BASE_URL,
    "submission_session_cookie": DEFAULT_SUBMISSION_SESSION_COOKIE,
    "submission_api_token": DEFAULT_SUBMISSION_API_TOKEN,
    "knowledge_repo_url": DEFAULT_KNOWLEDGE_REPO_URL,
}
LEGACY_TEST35_ENDPOINT_VALUES = {
    "server_profile": "test35",
    "submission_method": "ssh",
    "submission_ssh_host": "test35",
    "submission_command": "/home/test35/work/akbs/database-intake-worktree/scripts/akbs-submit",
    "submission_api_base_url": "",
    "submission_session_cookie": "",
    "submission_api_token": "",
    "knowledge_repo_url": "test35:/home/test35/work/akbs/knowledge.git",
}

CONFIG_DEFAULTS = {
    "default_profile": "",
    "profile": "",
    "server_profile": "",
    "role": "",
    "allowed_modes": "",
    "member_alias": "",
    "member_name": "",
    "knowledge_repo_url": "",
    "knowledge_repo_worktree": "",
    "submission_method": "",
    "submission_ssh_host": "",
    "submission_command": "",
    "submission_api_base_url": "",
    "submission_session_cookie": "",
    "submission_api_token": "",
    "git_user_name": "",
    "git_user_email": "",
    "codex_home": "$CODEX_HOME",
    "out_dir": "$CODEX_HOME/artifacts/android-knowledge-intake",
    "incoming_schema_version": "1",
    "include_patches": "true",
    "max_attachment_mb": "5",
    "timezone": "Asia/Shanghai",
    "synthetic_data": "false",
    "synthetic_item_count": "3",
}


def default_codex_home() -> str:
    return os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")


def expanded_path(value: str) -> Path:
    value = value.replace("$CODEX_HOME", default_codex_home())
    return Path(os.path.expandvars(os.path.expanduser(value)))


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def read_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib  # type: ignore[attr-defined]

        with path.open("rb") as fh:
            return tomllib.load(fh)
    except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
        return parse_simple_toml(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"读取配置失败: {path}: {exc}") from exc


def parse_toml_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        if not body:
            return []
        items = []
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


def stringify_config_value(value: Any) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def flatten_config_payload(payload: dict[str, Any]) -> dict[str, str]:
    flattened: dict[str, str] = {}

    def add(key: str, value: Any, section: str = "") -> None:
        if isinstance(value, dict):
            return
        normalized = key
        if section == "member" and key == "alias":
            normalized = "member_alias"
        elif section == "member" and key == "name":
            normalized = "member_name"
        elif section == "knowledge" and key in {"repo_url", "url", "knowledge_repo_url"}:
            normalized = "knowledge_repo_url"
        elif section == "knowledge" and key in {"repo_worktree", "worktree", "knowledge_repo_worktree"}:
            normalized = "knowledge_repo_worktree"
        elif section == "submission" and key in {"method", "submission_method"}:
            normalized = "submission_method"
        elif section == "submission" and key in {"ssh_host", "host", "submission_ssh_host"}:
            normalized = "submission_ssh_host"
        elif section == "submission" and key in {"command", "submit_command", "submission_command"}:
            normalized = "submission_command"
        elif section == "submission" and key in {"api_base_url", "base_url", "submission_api_base_url"}:
            normalized = "submission_api_base_url"
        elif section == "submission" and key in {"session_cookie", "cookie", "submission_session_cookie"}:
            normalized = "submission_session_cookie"
        elif section == "submission" and key in {"api_token", "token", "submission_api_token"}:
            normalized = "submission_api_token"
        elif section == "paths" and key in {"knowledge_repo_worktree", "knowledge_worktree"}:
            normalized = "knowledge_repo_worktree"
        elif section == "paths" and key in {"codex_home", "out_dir"}:
            normalized = key
        elif section == "git" and key in {"user_name", "name"}:
            normalized = "git_user_name"
        elif section == "git" and key in {"user_email", "email"}:
            normalized = "git_user_email"
        elif key == "person":
            normalized = "member_name"
        elif key == "name":
            normalized = "member_name"
        if normalized in CONFIG_DEFAULTS:
            flattened[normalized] = stringify_config_value(value)

    for key, value in payload.items():
        if key == "profiles":
            continue
        if isinstance(value, dict):
            for subkey, subvalue in value.items():
                add(str(subkey), subvalue, str(key))
        else:
            add(str(key), value)
    return flattened


def profile_configs(payload: dict[str, Any]) -> dict[str, dict[str, str]]:
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for name, profile_payload in profiles.items():
        if isinstance(profile_payload, dict):
            result[str(name)] = flatten_config_payload(profile_payload)
    return result


def find_project_report_config(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for directory in [current, *current.parents]:
        candidate = directory / ".codex" / "report.toml"
        if candidate.exists():
            return candidate
    return None


def profile_from_env() -> str:
    for prefix in ENV_PREFIXES:
        value = os.environ.get(f"{prefix}PROFILE")
        if value:
            return value
    return ""


def apply_env_overrides(config: dict[str, str]) -> None:
    aliases = {
        "MEMBER": "member_alias",
        "ALIAS": "member_alias",
        "PERSON": "member_name",
        "PERSON_NAME": "member_name",
        "MEMBER_NAME": "member_name",
        "KNOWLEDGE_WORKTREE": "knowledge_repo_worktree",
        "KNOWLEDGE_REPO_WORKTREE": "knowledge_repo_worktree",
        "SUBMISSION_API_BASE_URL": "submission_api_base_url",
        "SUBMISSION_SESSION_COOKIE": "submission_session_cookie",
        "SUBMISSION_API_TOKEN": "submission_api_token",
    }
    for env_key, value in os.environ.items():
        for prefix in ENV_PREFIXES:
            if not env_key.startswith(prefix):
                continue
            raw = env_key[len(prefix) :]
            key = aliases.get(raw, raw.lower())
            if key in config:
                config[key] = value


def akbs_endpoint_env_value(name: str) -> str:
    for prefix in AKBS_ENDPOINT_ENV_PREFIXES:
        value = os.environ.get(f"{prefix}{name.upper()}")
        if value:
            return value
    return ""


def resolve_akbs_endpoint(config: dict[str, str]) -> dict[str, str]:
    endpoint = dict(AKBS_ENDPOINT_DEFAULTS)
    endpoint["source"] = "default"
    env_keys = {
        "submission_api_base_url": "SUBMISSION_API_BASE_URL",
        "submission_session_cookie": "SUBMISSION_SESSION_COOKIE",
        "submission_api_token": "SUBMISSION_API_TOKEN",
    }
    env_overrides = {key: akbs_endpoint_env_value(env_key) for key, env_key in env_keys.items()}
    env_overrides = {key: value for key, value in env_overrides.items() if value}
    if env_overrides:
        endpoint.update(env_overrides)
        endpoint["source"] = "env_override"
        return endpoint

    role = str(config.get("role") or "").strip()
    configured = {
        key: str(config.get(key) or "").strip()
        for key in (
            "submission_api_base_url",
            "submission_session_cookie",
            "submission_api_token",
        )
        if str(config.get(key) or "").strip()
    }
    if role == "admin" and configured:
        endpoint.update(configured)
        endpoint["source"] = "admin_config_override"
    return endpoint


def configured_endpoint_fields(loaded: list[Path]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for path in loaded:
        if not path.exists():
            continue
        payload = read_toml(path)
        flattened = flatten_config_payload(payload)
        for key in (
            "server_profile",
            "submission_method",
            "submission_ssh_host",
            "submission_command",
            "submission_api_base_url",
            "submission_session_cookie",
            "submission_api_token",
            "knowledge_repo_url",
        ):
            value = str(flattened.get(key) or "").strip()
            if value:
                fields[key] = value
    return fields


def endpoint_migration_report(config: dict[str, str], loaded: list[Path]) -> dict[str, Any]:
    configured = configured_endpoint_fields(loaded)
    legacy_fields = sorted(
        key
        for key, value in configured.items()
        if value == LEGACY_TEST35_ENDPOINT_VALUES.get(key, "")
        or (
            key
            in {
                "submission_ssh_host",
                "knowledge_repo_url",
                "submission_command",
                "submission_api_base_url",
                "server_profile",
            }
            and "test35" in value
        )
    )
    custom_fields = sorted(key for key in configured if key not in legacy_fields)
    role = str(config.get("role") or "").strip()
    if not configured:
        status = "CURRENT"
        message = "普通成员配置未包含服务器入口字段，AKBS endpoint resolver 将提供上传入口和只读知识库入口。"
    elif role == "member" and legacy_fields and not custom_fields:
        status = "MIGRATED_IN_MEMORY"
        message = "检测到旧 test35 服务器硬编码；本次运行已在内存中迁移为 AKBS endpoint resolver 默认入口，未改成员身份字段。"
    elif role == "member":
        status = "MANUAL_ACTION_REQUIRED"
        message = "检测到普通成员配置中的自定义服务器字段；请移除这些字段，改由管理员/测试环境 endpoint override 提供。"
    else:
        status = "ADMIN_OVERRIDE"
        message = "检测到管理员/测试 endpoint override 配置；普通成员配置不应复制这些字段。"
    return {
        "status": status,
        "message": message,
        "legacy_fields": legacy_fields,
        "custom_fields": custom_fields,
    }


def load_config(profile_override: str | None = None) -> tuple[dict[str, str], list[Path]]:
    config = CONFIG_DEFAULTS.copy()
    codex_home = Path(default_codex_home())
    paths = [
        PLUGIN_ROOT / "config.toml",
        codex_home / "android-knowledge-intake.toml",
        codex_home / "report" / "config.toml",
    ]
    project_config = find_project_report_config()
    if project_config:
        paths.append(project_config)

    loaded: list[Path] = []
    profile_overrides: dict[str, dict[str, str]] = {}
    for path in paths:
        if not path.exists():
            continue
        loaded.append(path)
        payload = read_toml(path)
        for key, value in flatten_config_payload(payload).items():
            config[key] = value
        for name, values in profile_configs(payload).items():
            profile_overrides.setdefault(name, {}).update(values)

    selected_profile = (profile_override or profile_from_env() or config.get("default_profile", "")).strip()
    if selected_profile:
        if selected_profile not in profile_overrides:
            raise SystemExit(f"profile 不存在: {selected_profile}")
        config.update(profile_overrides[selected_profile])
        config["profile"] = selected_profile
    apply_env_overrides(config)
    return config, loaded


def require_config(config: dict[str, str]) -> None:
    missing = [key for key in ("member_alias", "member_name") if not config.get(key, "").strip()]
    if not submission_api_base_url(config):
        missing.append("submission_api_base_url")
    if missing:
        raise SystemExit("缺少必要配置: " + ", ".join(missing))


def knowledge_repo_url(config: dict[str, str]) -> str:
    return resolve_akbs_endpoint(config)["knowledge_repo_url"].strip()


def knowledge_repo_worktree(config: dict[str, str]) -> Path:
    value = config.get("knowledge_repo_worktree") or "$CODEX_HOME/worktrees/knowledge"
    return expanded_path(value)


def submission_api_base_url(config: dict[str, str]) -> str:
    return resolve_akbs_endpoint(config)["submission_api_base_url"].strip()


def submission_session_cookie(config: dict[str, str]) -> str:
    return resolve_akbs_endpoint(config)["submission_session_cookie"].strip()


def submission_api_token(config: dict[str, str]) -> str:
    return resolve_akbs_endpoint(config)["submission_api_token"].strip()


def allowed_modes(config: dict[str, str]) -> set[str]:
    raw = config.get("allowed_modes", "").strip()
    if not raw:
        return {"daily", "weekly", "patch"}
    modes = {item.strip() for item in raw.split(",") if item.strip()}
    invalid = modes - {"daily", "weekly", "patch"}
    if invalid:
        raise SystemExit("allowed_modes 包含非法类型: " + ", ".join(sorted(invalid)))
    return modes


def enforce_mode_allowed(config: dict[str, str], report_type: str) -> None:
    modes = allowed_modes(config)
    if report_type not in modes:
        profile = config.get("profile") or config.get("member_alias") or "<unknown>"
        raise SystemExit(f"profile {profile} 不允许执行 {report_type}，允许类型: {', '.join(sorted(modes))}")


def local_now(config: dict[str, str]) -> dt.datetime:
    tz_name = config.get("timezone", "Asia/Shanghai")
    if ZoneInfo is not None:
        try:
            return dt.datetime.now(ZoneInfo(tz_name))
        except Exception:
            pass
    return dt.datetime.now()


def parse_date_arg(value: str | None, config: dict[str, str]) -> dt.date:
    if value:
        return dt.date.fromisoformat(value)
    return local_now(config).date()
