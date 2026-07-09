from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .config import CONFIG_DEFAULTS, local_now
except ImportError:  # pragma: no cover - direct script import fallback
    scripts_root = Path(__file__).resolve().parents[1]
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))
    from akbs_intake.config import CONFIG_DEFAULTS, local_now


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_UPDATE_SKIP_ENV = "CODEX_REPORT_SKIP_PLUGIN_UPDATE_CHECK"
PLUGIN_UPDATE_REQUIRE_ENV = "CODEX_REPORT_REQUIRE_PLUGIN_UPDATE_CHECK"
PLUGIN_REEXEC_ATTEMPT_ENV = "CODEX_REPORT_PLUGIN_REEXEC_ATTEMPTED"
PLUGIN_REMOTE_MANIFEST_TIMEOUT = 6
LAST_PLUGIN_VERSION_GATE: dict[str, Any] | None = None


def run(cmd: list[str], check: bool = False, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        errors="replace",
    )
    if check and cp.returncode != 0:
        detail = cp.stderr.strip() or cp.stdout.strip()
        raise SystemExit(f"命令失败: {' '.join(cmd)}\n{detail}")
    return cp


def default_codex_home() -> str:
    if os.environ.get("CODEX_HOME"):
        return os.environ["CODEX_HOME"]
    return str(Path.home() / ".codex")


def expanded_path(value: str) -> Path:
    codex_home = default_codex_home()
    expanded = str(value).replace("${CODEX_HOME}", codex_home).replace("$CODEX_HOME", codex_home)
    return Path(os.path.expandvars(expanded)).expanduser()


def parse_bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def env_enabled(name: str) -> bool:
    return parse_bool(os.environ.get(name, ""))


def plugin_update_unknown(message: str, require: bool, git_root: Path | None = None, update_command: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "UNKNOWN",
        "blocking": require,
        "message": message,
    }
    if git_root is not None:
        payload["git_root"] = str(git_root)
    if update_command:
        payload["update_command"] = update_command
    if require:
        payload["message"] += " 已按强制策略停止本次生成；请先完成插件更新（plugin update）后重新运行原命令。"
    return payload


def plugin_manifest_path() -> Path | None:
    for directory in [PLUGIN_ROOT, *PLUGIN_ROOT.parents]:
        candidate = directory / ".codex-plugin" / "plugin.json"
        if candidate.is_file():
            return candidate
    return None


def plugin_install_metadata() -> dict[str, str]:
    manifest_path = plugin_manifest_path()
    payload: dict[str, Any] = {}
    if manifest_path:
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except Exception:
            payload = {}
    return {
        "plugin_name": str(payload.get("name") or "android-framework-ops"),
        "plugin_version": str(payload.get("version") or ""),
        "repository": str(payload.get("repository") or payload.get("homepage") or ""),
        "plugin_installation": "packaged" if manifest_path else "unknown",
    }


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def current_skill_cache_metadata() -> dict[str, str]:
    metadata = plugin_install_metadata()
    return {
        "skill_cache_version": metadata.get("plugin_version", ""),
        "skill_cache_path": str(PLUGIN_ROOT),
        "skill_cache_installation": metadata.get("plugin_installation", "unknown"),
    }


def latest_installed_plugin_cache_metadata(plugin_name: str = "android-framework-ops") -> dict[str, str]:
    codex_home = Path(default_codex_home())
    cache_root = codex_home / "plugins" / "cache"
    best: dict[str, str] = {}
    if not cache_root.is_dir():
        return best
    patterns = [
        f"*/{plugin_name}/*/.codex-plugin/plugin.json",
        f"*/{plugin_name}/.codex-plugin/plugin.json",
        f"{plugin_name}/*/.codex-plugin/plugin.json",
        f"{plugin_name}/.codex-plugin/plugin.json",
    ]
    for pattern in patterns:
        for manifest_path in cache_root.glob(pattern):
            payload = read_json_object(manifest_path)
            if str(payload.get("name") or plugin_name) != plugin_name:
                continue
            version = str(payload.get("version") or "")
            if not version:
                continue
            if not best or compare_versions(version, best.get("installed_plugin_version", "")) > 0:
                best = {
                    "installed_plugin_version": version,
                    "installed_plugin_path": str(manifest_path.parents[1] if manifest_path.parent.name == ".codex-plugin" else manifest_path.parent),
                }
    return best


def version_parts(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for item in str(value or "").split("."):
        match = re.match(r"^(\d+)", item)
        if match:
            parts.append(int(match.group(1)))
        else:
            parts.append(0)
    return tuple(parts)


def compare_versions(left: str, right: str) -> int:
    left_parts = list(version_parts(left))
    right_parts = list(version_parts(right))
    size = max(len(left_parts), len(right_parts), 1)
    left_parts.extend([0] * (size - len(left_parts)))
    right_parts.extend([0] * (size - len(right_parts)))
    return (left_parts > right_parts) - (left_parts < right_parts)


def github_raw_plugin_manifest_url(metadata: dict[str, str]) -> str:
    repository = str(metadata.get("repository") or "").strip().removesuffix(".git")
    match = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/#?]+)", repository)
    plugin_name = str(metadata.get("plugin_name") or "android-framework-ops").strip()
    if not match or not plugin_name:
        return ""
    owner = match.group("owner")
    repo = match.group("repo")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/main/plugins/{plugin_name}/.codex-plugin/plugin.json"


def fetch_remote_plugin_manifest(metadata: dict[str, str]) -> dict[str, Any]:
    url = github_raw_plugin_manifest_url(metadata)
    if not url:
        raise RuntimeError("插件仓库不是可识别的 GitHub 仓库，不能读取远端插件版本。")
    with urllib.request.urlopen(url, timeout=PLUGIN_REMOTE_MANIFEST_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("远端插件清单不是 JSON 对象。")
    return payload


def git_remote_plugin_version(git_root: Path, ref: str) -> str:
    manifest_path = plugin_manifest_path()
    if not manifest_path:
        return ""
    try:
        rel = manifest_path.resolve().relative_to(git_root.resolve()).as_posix()
    except ValueError:
        return ""
    cp = run(["git", "-C", str(git_root), "show", f"{ref}:{rel}"])
    if cp.returncode != 0:
        return ""
    try:
        payload = json.loads(cp.stdout)
    except Exception:
        return ""
    return str(payload.get("version") or "") if isinstance(payload, dict) else ""


def packaged_plugin_freshness(metadata: dict[str, str], fetch: bool, require: bool) -> dict[str, Any]:
    local_version = str(metadata.get("plugin_version") or "")
    cache_metadata = latest_installed_plugin_cache_metadata(metadata.get("plugin_name") or "android-framework-ops")
    skill_cache = current_skill_cache_metadata()
    payload: dict[str, Any] = {
        "status": "PASS" if local_version else "UNKNOWN",
        "blocking": False,
        "plugin_name": metadata.get("plugin_name") or "android-framework-ops",
        "local_version": local_version,
        "plugin_version": local_version,
        "skill_cache_version": skill_cache.get("skill_cache_version", ""),
        "skill_cache_path": skill_cache.get("skill_cache_path", ""),
        "installed_plugin_version": cache_metadata.get("installed_plugin_version", local_version),
        "installed_plugin_path": cache_metadata.get("installed_plugin_path", ""),
        "installation": metadata.get("plugin_installation") or "packaged",
        "message": "插件缓存版本已记录。",
    }
    if not local_version:
        return plugin_update_unknown("无法读取插件缓存版本，不能确认是否有更新。", require)
    installed_version = str(payload.get("installed_plugin_version") or "")
    if installed_version and compare_versions(local_version, installed_version) < 0:
        payload.update(
            {
                "status": "SESSION_CACHE_STALE",
                "blocking": True,
                "message": (
                    f"Codex 已安装 Android Framework Ops {installed_version}，但当前会话仍在使用过期技能缓存 {local_version}。"
                    "当前会话不能热刷新技能，请新开或重启 Codex 会话后再生成或上传。"
                ),
            }
        )
        return payload
    if not fetch:
        return payload
    try:
        remote_manifest = fetch_remote_plugin_manifest(metadata)
    except Exception as exc:
        return plugin_update_unknown(f"无法读取插件远端版本，不能确认是否有更新: {exc}", require)
    remote_version = str(remote_manifest.get("version") or "")
    payload["remote_version"] = remote_version
    payload["remote_plugin_version"] = remote_version
    if remote_version and compare_versions(local_version, remote_version) < 0:
        auto_update = auto_update_packaged_plugin(str(metadata.get("plugin_name") or "android-framework-ops"))
        payload["auto_update"] = auto_update
        if auto_update.get("status") == "PASS":
            payload.update(
                {
                    "status": "UPDATED_RESTART_REQUIRED",
                    "blocking": True,
                    "message": (
                        f"Codex 插件缓存已自动更新到 Android Framework Ops {remote_version}。"
                        "当前 Python 进程和 Codex 会话已经加载了过期技能缓存，当前会话不能热刷新；"
                        "请重新运行原命令，并在 Codex 会话仍显示旧技能时新开或重启会话。"
                    ),
                }
            )
            return payload
        payload.update(
            {
                "status": "STALE",
                "blocking": True,
                "message": (
                    f"GitHub 已发布 Android Framework Ops {remote_version}，当前插件缓存是 {local_version}。"
                    "自动更新插件缓存失败，请先在 Codex 插件市场更新插件；如果已更新但当前会话仍显示旧版本，请新开或重启会话后再生成或上传。"
                ),
            }
        )
    elif remote_version:
        payload["message"] = "插件缓存版本已是当前远端版本。"
    else:
        payload.update(
            {
                "status": "UNKNOWN",
                "blocking": require,
                "message": "远端插件清单缺少版本号，不能确认是否有更新。",
            }
        )
    return payload


def auto_update_packaged_plugin(plugin_name: str) -> dict[str, Any]:
    marketplace = "android-framework-codex-suite"
    upgrade_cmd = ["codex", "plugin", "marketplace", "upgrade", marketplace, "--json"]
    add_cmd = ["codex", "plugin", "add", f"{plugin_name}@{marketplace}", "--json"]
    upgrade_cp = run(upgrade_cmd)
    if upgrade_cp.returncode != 0:
        return {
            "attempted": True,
            "status": "FAIL",
            "upgrade_command": shlex.join(upgrade_cmd),
            "stderr": upgrade_cp.stderr.strip(),
            "stdout": upgrade_cp.stdout.strip(),
        }
    add_cp = run(add_cmd)
    if add_cp.returncode != 0:
        return {
            "attempted": True,
            "status": "FAIL",
            "upgrade_command": shlex.join(upgrade_cmd),
            "install_command": shlex.join(add_cmd),
            "marketplace_stdout": upgrade_cp.stdout.strip(),
            "stderr": add_cp.stderr.strip(),
            "stdout": add_cp.stdout.strip(),
        }
    payload = {
        "attempted": True,
        "status": "PASS",
        "upgrade_command": shlex.join(upgrade_cmd),
        "install_command": shlex.join(add_cmd),
        "marketplace_stdout": upgrade_cp.stdout.strip(),
        "install_stdout": add_cp.stdout.strip(),
    }
    payload.update(latest_installed_plugin_cache_metadata(plugin_name))
    return payload


def plugin_intake_script_from_root(root: Path) -> Path:
    if root.name == "android-knowledge-intake" and root.parent.name == "skills":
        return root / "scripts" / "android_knowledge_intake.py"
    return root / "skills" / "android-knowledge-intake" / "scripts" / "android_knowledge_intake.py"


def updated_plugin_intake_script_path(freshness: dict[str, Any]) -> Path | None:
    auto_update = freshness.get("auto_update") if isinstance(freshness.get("auto_update"), dict) else {}
    plugin_name = str(freshness.get("plugin_name") or "android-framework-ops")
    root_values = [
        auto_update.get("installed_plugin_path"),
        freshness.get("installed_plugin_path"),
    ]
    cache_metadata = latest_installed_plugin_cache_metadata(plugin_name)
    if cache_metadata.get("installed_plugin_path"):
        root_values.append(cache_metadata["installed_plugin_path"])

    for root_value in root_values:
        if not root_value:
            continue
        script_path = plugin_intake_script_from_root(Path(str(root_value))).resolve()
        if script_path.is_file():
            return script_path

    if auto_update.get("status") == "PASS" and auto_update.get("command"):
        return Path(__file__).resolve()
    return None


def reexec_latest_plugin_script_after_update(freshness: dict[str, Any]) -> str:
    if freshness.get("status") not in {"UPDATED_RESTART_REQUIRED", "SESSION_CACHE_STALE"}:
        return ""
    if os.environ.get(PLUGIN_REEXEC_ATTEMPT_ENV):
        return ""
    script_path = updated_plugin_intake_script_path(freshness)
    if not script_path:
        return "已更新插件缓存，但未找到新缓存里的上传脚本；请新开或重启 Codex 会话后重新运行。"
    os.environ[PLUGIN_REEXEC_ATTEMPT_ENV] = "1"
    try:
        os.execv(sys.executable, [sys.executable, str(script_path), *sys.argv[1:]])
    except OSError as exc:
        return f"已更新插件缓存，但无法切换到新脚本继续执行: {exc}。请新开或重启 Codex 会话后重新运行。"
    return ""


def plugin_freshness_check(fetch: bool = True, require: bool = False) -> dict[str, Any]:
    require = require or env_enabled(PLUGIN_UPDATE_REQUIRE_ENV)
    if env_enabled(PLUGIN_UPDATE_SKIP_ENV):
        return {
            "status": "SKIPPED",
            "blocking": False,
            "message": "已按环境变量跳过插件更新检查（plugin update check）。",
        }

    root_cp = run(["git", "-C", str(PLUGIN_ROOT), "rev-parse", "--show-toplevel"])
    if root_cp.returncode != 0:
        metadata = plugin_install_metadata()
        if metadata.get("plugin_version"):
            return packaged_plugin_freshness(metadata, fetch, require)
        return plugin_update_unknown(
            "无法确认插件版本：当前插件目录不是 Git 仓库（git repository）。请在 Codex 插件市场更新 Android Framework Ops 插件后重新运行。",
            require,
        )
    git_root = Path(root_cp.stdout.strip()).resolve()
    update_command = shlex.join(["git", "-C", str(git_root), "pull", "--ff-only"])

    branch_cp = run(["git", "-C", str(git_root), "rev-parse", "--abbrev-ref", "HEAD"])
    if branch_cp.returncode != 0:
        return plugin_update_unknown("无法读取插件当前分支，不能确认是否有更新。", require, git_root, update_command)
    branch = branch_cp.stdout.strip()
    if branch == "HEAD":
        return plugin_update_unknown("插件仓库处于 detached HEAD 状态，不能自动判断远端更新。", require, git_root, update_command)

    remote_cp = run(["git", "-C", str(git_root), "config", "--get", f"branch.{branch}.remote"])
    remote_name = remote_cp.stdout.strip() if remote_cp.returncode == 0 else ""
    if not remote_name:
        origin_cp = run(["git", "-C", str(git_root), "config", "--get", "remote.origin.url"])
        if origin_cp.returncode == 0 and origin_cp.stdout.strip():
            remote_name = "origin"
    if not remote_name:
        return plugin_update_unknown("插件仓库没有配置远端仓库，不能确认是否有更新。", require, git_root, update_command)

    if fetch:
        fetch_cp = run(["git", "-C", str(git_root), "fetch", "--quiet", remote_name])
        if fetch_cp.returncode != 0:
            detail = (fetch_cp.stderr.strip() or fetch_cp.stdout.strip()).splitlines()
            suffix = f": {detail[0]}" if detail else ""
            return plugin_update_unknown(f"无法访问插件远端仓库，不能确认是否有更新{suffix}", require, git_root, update_command)

    local_cp = run(["git", "-C", str(git_root), "rev-parse", "HEAD"])
    if local_cp.returncode != 0:
        return plugin_update_unknown("无法读取插件本地提交，不能确认是否有更新。", require, git_root, update_command)
    local_commit = local_cp.stdout.strip()

    upstream_cp = run(["git", "-C", str(git_root), "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    upstream_ref = upstream_cp.stdout.strip() if upstream_cp.returncode == 0 else ""
    if not upstream_ref:
        for candidate in (f"{remote_name}/{branch}", "origin/main", "origin/master"):
            candidate_cp = run(["git", "-C", str(git_root), "rev-parse", "--verify", candidate])
            if candidate_cp.returncode == 0:
                upstream_ref = candidate
                break
    if not upstream_ref:
        return plugin_update_unknown("插件仓库没有可比较的上游分支，不能确认是否有更新。", require, git_root, update_command)

    remote_commit_cp = run(["git", "-C", str(git_root), "rev-parse", upstream_ref])
    if remote_commit_cp.returncode != 0:
        return plugin_update_unknown("无法读取插件远端提交，不能确认是否有更新。", require, git_root, update_command)
    remote_commit = remote_commit_cp.stdout.strip()

    dirty_cp = run(["git", "-C", str(git_root), "status", "--porcelain"])
    warnings: list[str] = []
    if dirty_cp.returncode == 0 and dirty_cp.stdout.strip():
        warnings.append("插件仓库存在未提交改动，更新前需要先处理本地改动。")

    payload: dict[str, Any] = {
        "git_root": str(git_root),
        "local_commit": local_commit[:12],
        "remote_ref": upstream_ref,
        "remote_commit": remote_commit[:12],
        "update_command": update_command,
    }
    metadata = plugin_install_metadata()
    if metadata.get("plugin_version"):
        payload["local_version"] = metadata["plugin_version"]
        payload["plugin_version"] = metadata["plugin_version"]
        payload["skill_cache_version"] = metadata["plugin_version"]
    remote_version = git_remote_plugin_version(git_root, upstream_ref)
    if remote_version:
        payload["remote_version"] = remote_version
        payload["remote_plugin_version"] = remote_version
    cache_metadata = latest_installed_plugin_cache_metadata(metadata.get("plugin_name") or "android-framework-ops")
    if cache_metadata:
        payload.update(cache_metadata)
    if warnings:
        payload["warnings"] = warnings

    if local_commit == remote_commit:
        local_version = str(payload.get("local_version") or "")
        installed_version = str(payload.get("installed_plugin_version") or "")
        if installed_version and local_version and compare_versions(local_version, installed_version) < 0:
            payload.update(
                {
                    "status": "SESSION_CACHE_STALE",
                    "blocking": True,
                    "message": (
                        f"Codex 已安装 Android Framework Ops {installed_version}，但当前会话仍在使用过期技能缓存 {local_version}。"
                        "当前会话不能热刷新技能，请新开或重启 Codex 会话后再生成或上传。"
                    ),
                }
            )
            return payload
        payload.update(
            {
                "status": "PASS",
                "blocking": False,
                "message": "插件已是当前远端版本。",
            }
        )
        return payload

    local_ancestor = run(["git", "-C", str(git_root), "merge-base", "--is-ancestor", local_commit, remote_commit])
    if local_ancestor.returncode == 0:
        if warnings:
            payload.update(
                {
                    "status": "STALE",
                    "blocking": True,
                    "message": "插件有更新，但当前插件仓库存在未提交改动，不能自动更新。请先处理本地改动后重新运行。",
                }
            )
            return payload
        pull_cp = run(["git", "-C", str(git_root), "pull", "--ff-only"])
        if pull_cp.returncode == 0:
            payload["auto_update"] = {
                "attempted": True,
                "status": "PASS",
                "command": update_command,
                "stdout": pull_cp.stdout.strip(),
            }
            payload.update(
                {
                    "status": "UPDATED_RESTART_REQUIRED",
                    "blocking": True,
                    "message": (
                        "插件已自动快进更新。当前 Python 进程和 Codex 会话已经加载了过期技能缓存，不能热刷新；"
                        "请重新运行原命令，并在 Codex 会话仍显示旧技能时新开或重启会话。"
                    ),
                }
            )
            return payload
        payload["auto_update"] = {
            "attempted": True,
            "status": "FAIL",
            "command": update_command,
            "stderr": pull_cp.stderr.strip(),
            "stdout": pull_cp.stdout.strip(),
        }
        payload.update(
            {
                "status": "STALE",
                "blocking": True,
                "message": "插件有更新，但自动快进更新失败，已停止本次生成。请先执行插件更新（plugin update）后重新运行原命令。",
            }
        )
        return payload

    remote_ancestor = run(["git", "-C", str(git_root), "merge-base", "--is-ancestor", remote_commit, local_commit])
    if remote_ancestor.returncode == 0:
        payload.update(
            {
                "status": "PASS",
                "blocking": False,
                "message": "本地插件提交领先远端，未发现必须先拉取的更新。",
            }
        )
        return payload

    payload.update(
        {
            "status": "DIVERGED",
            "blocking": True,
            "message": "插件本地分支和远端分支已分叉，已停止本次生成。请让管理员处理插件更新（plugin update）后重新运行原命令。",
        }
    )
    return payload


def plugin_version_gate_check(config: dict[str, str] | None = None, fetch: bool = True, require: bool = True) -> dict[str, Any]:
    global LAST_PLUGIN_VERSION_GATE
    gate = plugin_freshness_check(fetch=fetch, require=require)
    metadata = plugin_install_metadata()
    skill_cache = current_skill_cache_metadata()
    cache_metadata = latest_installed_plugin_cache_metadata(metadata.get("plugin_name") or "android-framework-ops")
    gate.setdefault("plugin_name", metadata.get("plugin_name") or "android-framework-ops")
    gate.setdefault("plugin_version", metadata.get("plugin_version") or "")
    gate.setdefault("local_version", metadata.get("plugin_version") or "")
    gate.setdefault("skill_cache_version", skill_cache.get("skill_cache_version", ""))
    gate.setdefault("skill_cache_path", skill_cache.get("skill_cache_path", ""))
    if cache_metadata:
        gate.setdefault("installed_plugin_version", cache_metadata.get("installed_plugin_version", ""))
        gate.setdefault("installed_plugin_path", cache_metadata.get("installed_plugin_path", ""))
    gate["checked_at"] = local_now(config or CONFIG_DEFAULTS).isoformat()
    gate["result"] = gate.get("status", "UNKNOWN")
    LAST_PLUGIN_VERSION_GATE = gate
    return gate
