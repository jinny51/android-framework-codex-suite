from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from android_framework_ops.artifact_paths import require_safe_artifact_path


ROOT_MARKERS = (
    Path("index") / "case-index.jsonl",
    Path("index") / "variant-index.jsonl",
    Path("index") / "symbol-index.jsonl",
    Path("index") / "evidence-index.jsonl",
    Path("index") / "search-docs.jsonl",
)
ENV_PREFIXES = ("CODEX_KNOWLEDGE_", "CODEX_REPORT_", "CODEX_WORK_REPORT_")
AKBS_ENDPOINT_ENV_PREFIXES = ("CODEX_REPORT_AKBS_ENDPOINT_", "CODEX_WORK_REPORT_AKBS_ENDPOINT_")
DEFAULT_AKBS_API_BASE_URL = "http://192.168.100.118:8088"
MEMBER_SEARCH_PATH = "/akbs/api/member/knowledge-search"
MEMBER_MERGE_CONFIRMATIONS_PATH = "/akbs/api/member/me/merge-confirmations"


def expand_path(value: str | os.PathLike[str]) -> Path:
    codex_home_value = os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    text = str(value).replace("${CODEX_HOME}", codex_home_value).replace("$CODEX_HOME", codex_home_value)
    return Path(os.path.expandvars(os.path.expanduser(text))).resolve()


def codex_home() -> Path:
    return expand_path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


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


def read_toml(path: Path) -> dict[str, Any]:
    try:
        try:
            import tomllib

            return tomllib.loads(path.read_text(encoding="utf-8"))
        except ModuleNotFoundError:
            return parse_simple_toml(path.read_text(encoding="utf-8"))
    except Exception:
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


def selected_profile(payload: dict[str, Any]) -> str:
    for prefix in ENV_PREFIXES:
        value = os.environ.get(f"{prefix}PROFILE")
        if value:
            return value
    value = payload.get("default_profile", "")
    return str(value).strip() if value else ""


def configured_worktree_values(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    add(payload.get("knowledge_repo_worktree"))
    knowledge = payload.get("knowledge")
    if isinstance(knowledge, dict):
        add(knowledge.get("worktree"))
        add(knowledge.get("repo_worktree"))
        add(knowledge.get("knowledge_repo_worktree"))
    paths = payload.get("paths")
    if isinstance(paths, dict):
        add(paths.get("knowledge_worktree"))
        add(paths.get("knowledge_repo_worktree"))
    profiles = payload.get("profiles")
    profile = selected_profile(payload)
    if profile and isinstance(profiles, dict):
        profile_payload = profiles.get(profile)
        if isinstance(profile_payload, dict):
            add(profile_payload.get("knowledge_repo_worktree"))
            add(profile_payload.get("knowledge_worktree"))
    return values


def configured_roots() -> list[Path]:
    roots: list[Path] = []
    for env_key in (
        "CODEX_KNOWLEDGE_REPO_WORKTREE",
        "CODEX_REPORT_KNOWLEDGE_REPO_WORKTREE",
    ):
        if os.environ.get(env_key):
            roots.append(expand_path(os.environ[env_key]))

    home = codex_home()
    config_paths = [
        home / "android-knowledge-search.toml",
        home / "report" / "config.toml",
    ]
    project_config = find_project_report_config()
    if project_config:
        config_paths.append(project_config)

    for path in config_paths:
        if not path.exists():
            continue
        for value in configured_worktree_values(read_toml(path)):
            roots.append(expand_path(value))
    return roots


def config_payloads() -> list[dict[str, Any]]:
    home = codex_home()
    config_paths = [
        home / "android-knowledge-search.toml",
        home / "report" / "config.toml",
    ]
    project_config = find_project_report_config()
    if project_config:
        config_paths.append(project_config)

    payloads: list[dict[str, Any]] = []
    for path in config_paths:
        if path.exists():
            payloads.append(read_toml(path))
    return payloads


def selected_profile_payload(payload: dict[str, Any]) -> dict[str, Any]:
    profile = selected_profile(payload)
    profiles = payload.get("profiles")
    if profile and isinstance(profiles, dict):
        profile_payload = profiles.get(profile)
        if isinstance(profile_payload, dict):
            return profile_payload
    return {}


def configured_endpoint_values(payload: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}

    def add(key: str, value: Any) -> None:
        if isinstance(value, str) and value.strip():
            values[key] = value.strip()

    def add_section(section: Any) -> None:
        if not isinstance(section, dict):
            return
        add("member_search_url", section.get("member_search_url"))
        add("api_base_url", section.get("api_base_url"))

    add("member_search_url", payload.get("member_search_url"))
    add("api_base_url", payload.get("api_base_url"))
    add_section(payload.get("akbs_endpoint"))
    add_section(payload.get("endpoint"))

    profile_payload = selected_profile_payload(payload)
    role = str(profile_payload.get("role") or payload.get("role") or "").strip()
    if role == "admin":
        add("member_search_url", profile_payload.get("member_search_url"))
        add("api_base_url", profile_payload.get("api_base_url"))
        add_section(profile_payload.get("akbs_endpoint"))
        add_section(profile_payload.get("endpoint"))
    return values


def configured_out_dir_values(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            values.append(value.strip())

    add(payload.get("out_dir"))
    paths = payload.get("paths")
    if isinstance(paths, dict):
        add(paths.get("out_dir"))
    profiles = payload.get("profiles")
    profile = selected_profile(payload)
    if profile and isinstance(profiles, dict):
        profile_payload = profiles.get(profile)
        if isinstance(profile_payload, dict):
            add(profile_payload.get("out_dir"))
    return values


def search_usage_root(config_payloads_fn: Callable[[], list[dict[str, Any]]] = config_payloads) -> Path:
    for payload in config_payloads_fn():
        for value in configured_out_dir_values(payload):
            return require_safe_artifact_path(expand_path(value) / "search-usage", purpose="search usage output")
    return require_safe_artifact_path(codex_home() / "artifacts" / "android-knowledge-intake" / "search-usage", purpose="search usage output")


def selected_member_alias() -> tuple[str, str]:
    for payload in config_payloads():
        profile = selected_profile(payload)
        profiles = payload.get("profiles")
        if profile and isinstance(profiles, dict):
            profile_payload = profiles.get(profile)
            if isinstance(profile_payload, dict):
                alias = str(profile_payload.get("member_alias") or "").strip()
                if alias:
                    return profile, alias
        alias = str(payload.get("member_alias") or "").strip()
        if alias:
            return profile, alias
    return "", ""


def akbs_endpoint_env_value(name: str) -> str:
    for prefix in AKBS_ENDPOINT_ENV_PREFIXES:
        value = os.environ.get(f"{prefix}{name.upper()}")
        if value:
            return value.strip()
    return ""


def member_search_endpoint_url() -> tuple[str, str]:
    explicit = akbs_endpoint_env_value("MEMBER_SEARCH_URL")
    if explicit:
        return explicit, "env_override"
    env_base = akbs_endpoint_env_value("API_BASE_URL")
    if env_base:
        return env_base.rstrip("/") + MEMBER_SEARCH_PATH, "env_override"
    for payload in config_payloads():
        configured = configured_endpoint_values(payload)
        if configured.get("member_search_url"):
            return configured["member_search_url"], "admin_config_override"
        if configured.get("api_base_url"):
            return configured["api_base_url"].rstrip("/") + MEMBER_SEARCH_PATH, "admin_config_override"
    base = DEFAULT_AKBS_API_BASE_URL
    return base.rstrip("/") + MEMBER_SEARCH_PATH, "default"


def member_api_base_url() -> tuple[str, str]:
    env_base = akbs_endpoint_env_value("API_BASE_URL")
    if env_base:
        return env_base.rstrip("/"), "env_override"
    for payload in config_payloads():
        configured = configured_endpoint_values(payload)
        if configured.get("api_base_url"):
            return configured["api_base_url"].rstrip("/"), "admin_config_override"
    search_url, source = member_search_endpoint_url()
    if search_url.endswith(MEMBER_SEARCH_PATH):
        return search_url[: -len(MEMBER_SEARCH_PATH)].rstrip("/"), source
    parsed = urllib.parse.urlsplit(search_url)
    if parsed.scheme and parsed.netloc:
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/"), source
    return DEFAULT_AKBS_API_BASE_URL, "default"


def member_merge_confirmations_url(identifier: str = "", action: str = "") -> str:
    base, _source = member_api_base_url()
    path = MEMBER_MERGE_CONFIRMATIONS_PATH
    if identifier:
        path += "/" + urllib.parse.quote(identifier, safe="")
    if action:
        path += "/" + action.strip("/")
    return base.rstrip("/") + path
