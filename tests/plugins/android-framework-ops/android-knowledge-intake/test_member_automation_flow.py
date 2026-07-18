from __future__ import annotations

import datetime as dt
import contextlib
import http.server
import importlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import textwrap
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


SUITE_ROOT = Path(__file__).resolve().parents[4]
INTAKE_SCRIPT = SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "scripts" / "android_knowledge_intake.py"
CAPTURE_SCRIPT = SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-framework-patch-capture" / "scripts" / "capture_framework_patch.py"
SETUP_PROMPT = SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "references" / "member-setup-prompt.md"
MEMBER_BOUNDARY_DOCS = (
    SUITE_ROOT / "README.md",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "README.md",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "SKILL.md",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "agents" / "openai.yaml",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "config.example.toml",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "references" / "incoming-package-protocol.md",
    SETUP_PROMPT,
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-framework-patch-capture" / "SKILL.md",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-framework-patch-capture" / "references" / "package-contract.md",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-search" / "SKILL.md",
    SUITE_ROOT / "docs" / "skills" / "android-framework-ops" / "android-knowledge-intake" / "README.md",
    SUITE_ROOT / "docs" / "skills" / "android-framework-ops" / "android-framework-patch-capture" / "README.md",
    SUITE_ROOT / "docs" / "skills" / "android-framework-ops" / "android-knowledge-search" / "README.md",
)
SESSION_CONSENT_ARGS = [
    "--session-consent",
    "--session-field",
    "work_summary",
    "--session-field",
    "project_hint",
    "--session-field",
    "command_summary",
    "--session-field",
    "patch_discovery",
]


def successful_upload_payload() -> dict[str, object]:
    return {
        "submitted": True,
        "accepted": True,
        "agent_context": {
            "incoming_contract": {
                "schema": "knowledge-incoming-package",
                "version": "1",
                "result": "PASS",
                "reason_codes": ["server_contract_v1_pass"],
                "authority": "akbs-server",
            }
        },
    }


def load_intake_module():
    name = "android_knowledge_intake_under_test"
    spec = importlib.util.spec_from_file_location(name, INTAKE_SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载脚本: {INTAKE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        errors="replace",
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result


def run_json(cmd: list[str], cwd: Path, env: dict[str, str], check: bool = True) -> dict:
    result = run(cmd, cwd, env, check=check)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - failure diagnostics
        raise AssertionError(result.stdout + result.stderr) from exc


def seed_knowledge_remote(root: Path) -> Path:
    remote = root / "knowledge.git"
    seed = root / "seed"
    run(["git", "init", "--bare", str(remote)], root)
    run(["git", "init", str(seed)], root)
    run(["git", "config", "user.email", "seed@example.invalid"], seed)
    run(["git", "config", "user.name", "Seed User"], seed)
    (seed / "README.md").write_text("# knowledge test remote\n", encoding="utf-8")
    run(["git", "add", "README.md"], seed)
    run(["git", "commit", "-m", "seed"], seed)
    run(["git", "branch", "-M", "main"], seed)
    run(["git", "remote", "add", "origin", str(remote)], seed)
    run(["git", "push", "-u", "origin", "main"], seed)
    run(["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], root)
    return remote


def seed_stale_plugin_checkout(root: Path) -> Path:
    remote = root / "plugin-origin.git"
    seed = root / "plugin-seed"
    checkout = root / "plugin-checkout"
    skill_root = checkout / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake"
    seed_skill_root = seed / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake"

    run(["git", "init", "--bare", str(remote)], root)
    run(["git", "init", str(seed)], root)
    run(["git", "config", "user.email", "plugin@example.invalid"], seed)
    run(["git", "config", "user.name", "Plugin User"], seed)
    seed_skill_root.mkdir(parents=True)
    (seed_skill_root / "marker.txt").write_text("version 1\n", encoding="utf-8")
    run(["git", "add", "."], seed)
    run(["git", "commit", "-m", "plugin seed"], seed)
    run(["git", "branch", "-M", "main"], seed)
    run(["git", "remote", "add", "origin", str(remote)], seed)
    run(["git", "push", "-u", "origin", "main"], seed)
    run(["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"], root)
    run(["git", "clone", str(remote), str(checkout)], root)

    (seed_skill_root / "marker.txt").write_text("version 2\n", encoding="utf-8")
    run(["git", "add", "."], seed)
    run(["git", "commit", "-m", "plugin update"], seed)
    run(["git", "push"], seed)
    return skill_root


def seed_packaged_plugin_install(root: Path, version: str = "1.0.24") -> Path:
    plugin_root = root / "codex-plugin-cache" / "android-framework-ops" / version
    skill_root = plugin_root / "skills" / "android-knowledge-intake"
    skill_root.mkdir(parents=True)
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "name": "android-framework-ops",
                "version": version,
                "repository": "https://github.com/jinny51/android-framework-codex-suite",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return skill_root


def seed_codex_plugin_cache(codex_home: Path, version: str) -> Path:
    plugin_root = codex_home / "plugins" / "cache" / "android-framework-codex-suite" / "android-framework-ops" / version
    skill_root = plugin_root / "skills" / "android-knowledge-intake"
    skill_root.mkdir(parents=True)
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "name": "android-framework-ops",
                "version": version,
                "repository": "https://github.com/jinny51/android-framework-codex-suite",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return skill_root


@contextlib.contextmanager
def fake_upload_server():
    received: list[dict[str, object]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            target = "20260601/member01/20260601-230000-patch"
            if "/packages/" in self.path:
                payload = {
                    "package_key": target,
                    "member_alias": "member01",
                    "submitted_at": "2026-06-01T23:00:00+08:00",
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("X-Request-ID", "req_11111111111111111111111111111111")
                self.end_headers()
                self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                return
            payload = {
                "total": 1,
                "items": [
                    {
                        "notice_id": "akbs-archive-supplement:review-test",
                        "review_id": "review-test",
                        "member_alias": "member01",
                        "state": "needs_evidence",
                        "supplement_for_package_key": target,
                        "lifecycle": {
                            "facts": {
                                "supplement_request": {
                                    "request_id": "supplement-request-test",
                                    "status": "open",
                                    "mode": "field_correction",
                                    "target_package_key": target,
                                }
                            }
                        },
                    }
                ],
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("X-Request-ID", "req_0123456789abcdef0123456789abcdef")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length)
            received.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body_length": len(body),
                }
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("X-Request-ID", "req_fedcba9876543210fedcba9876543210")
            self.end_headers()
            self.wfile.write(json.dumps(successful_upload_payload(), ensure_ascii=False).encode("utf-8"))

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/akbs/api", received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def write_member_config(root: Path, knowledge_remote: Path, synthetic_data: bool = True) -> dict[str, str]:
    codex_home = root / "codex-home"
    config_dir = codex_home / "report"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        textwrap.dedent(
            f"""
            default_profile = "member01"
            incoming_schema_version = "1"

            [paths]
            out_dir = "{(root / "artifacts" / "android-knowledge-intake").as_posix()}"

            [profiles.member01]
            member_alias = "member01"
            member_name = "成员甲"
            role = "member"
            allowed_modes = ["daily", "weekly", "patch"]
            knowledge_repo_worktree = "{(root / "worktrees" / "knowledge").as_posix()}"
            git_user_name = "成员甲"
            git_user_email = "member01@example.invalid"
            synthetic_data = {str(synthetic_data).lower()}
            synthetic_item_count = "2"
            weekly_history_api_enabled = false
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    env["CODEX_REPORT_SKIP_PLUGIN_UPDATE_CHECK"] = "1"
    return env


def clone_member_knowledge_worktree(root: Path, knowledge_remote: Path) -> Path:
    worktree = root / "worktrees" / "knowledge"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", str(knowledge_remote), str(worktree)], root)
    return worktree


def write_codex_session(
    codex_home: Path,
    session_id: str,
    cwd: Path,
    date: dt.date,
    message: str | list[str],
    thread_name: str = "SystemUI 状态栏策略修改",
    commands: list[str] | None = None,
) -> None:
    sessions_dir = codex_home / "sessions" / f"{date:%Y}" / f"{date:%m}" / f"{date:%d}"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    index = codex_home / "session_index.jsonl"
    with index.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"id": session_id, "thread_name": thread_name}, ensure_ascii=False) + "\n")
    rows = [
        {
            "timestamp": f"{date.isoformat()}T10:00:00+08:00",
            "type": "session_meta",
            "payload": {"id": session_id, "cwd": str(cwd)},
        }
    ]
    for index, text in enumerate([message] if isinstance(message, str) else message, start=1):
        rows.append(
            {
                "timestamp": f"{date.isoformat()}T10:{index:02d}:00+08:00",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )
    for index, cmd in enumerate(commands or [], start=30):
        rows.append(
            {
                "timestamp": f"{date.isoformat()}T10:{index:02d}:00+08:00",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "arguments": json.dumps({"cmd": cmd}, ensure_ascii=False),
                },
            }
        )
    (sessions_dir / f"{session_id}.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def read_package_report(package: Path, report_type: str = "daily") -> str:
    return (package / "reports" / f"{report_type}.md").read_text(encoding="utf-8")


def read_package_findings(package: Path) -> dict:
    return json.loads((package / "materials" / "evidence" / "work_findings.json").read_text(encoding="utf-8"))


def read_report_view(package: Path) -> dict:
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    display_paths = manifest.get("files", {}).get("display", [])
    assert display_paths
    return json.loads((package / display_paths[0]).read_text(encoding="utf-8"))


def prepare_daily_package(env: dict[str, str], date: str, run_id: str) -> Path:
    result = run_json(
        [
            sys.executable,
            str(INTAKE_SCRIPT),
            "--profile",
            "member01",
            "daily",
            "--date",
            date,
            "--run-id",
            run_id,
            *SESSION_CONSENT_ARGS,
            "--prepare",
        ],
        SUITE_ROOT,
        env,
    )
    return Path(result["package"])


def prepare_weekly_package(env: dict[str, str], date: str, run_id: str, weekly_facts: Path | None = None) -> Path:
    facts_args = ["--weekly-facts", str(weekly_facts)] if weekly_facts else []
    result = run_json(
        [
            sys.executable,
            str(INTAKE_SCRIPT),
            "--profile",
            "member01",
            "weekly",
            "--date",
            date,
            "--run-id",
            run_id,
            *facts_args,
            *SESSION_CONSENT_ARGS,
            "--prepare",
        ],
        SUITE_ROOT,
        env,
    )
    return Path(result["package"])


def write_weekly_facts(path: Path, week_range: str = "20260601-20260607") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "akbs-weekly-project-facts-v2",
                "week_range": week_range,
                "projects": [
                    {
                        "project": "TVE1086U",
                        "customer": "青鸾云",
                        "project_role": "主责",
                        "week_summary": "本周完成状态栏策略修改和设备验证。",
                        "requirement_date": "2026-05-18",
                        "requirement_source": "CR",
                        "requirement_structure": {"demand": 5, "migration": 3, "bug": 3, "bsp": 1},
                        "completed_this_week": {"demand": 1, "migration": 1, "bug": 1},
                        "remaining": {"demand": 1, "migration": 1, "bsp": 1},
                        "completed_items": ["状态栏策略修改", "设备验证", "修复亮度同步问题"],
                        "remaining_items": ["补齐客户验收", "完成 BSP 联调", "收敛配置项"],
                        "key_points": ["完成状态栏策略关键问题收敛"],
                        "risks": ["BSP 联调环境尚未就绪"],
                        "dependencies": ["等待 BSP 提供新固件"],
                        "next_week_plan": ["完成 BSP 联调并提交客户验收"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def prepare_replacement_package(env: dict[str, str], report_type: str, date: str, run_id: str, replacement_run_id: str) -> Path:
    option = "--replace-daily-run-id" if report_type == "daily" else "--replace-weekly-run-id"
    result = run_json(
        [
            sys.executable,
            str(INTAKE_SCRIPT),
            "--profile",
            "member01",
            report_type,
            "--date",
            date,
            "--run-id",
            run_id,
            option,
            replacement_run_id,
            *SESSION_CONSENT_ARGS,
            "--prepare",
        ],
        SUITE_ROOT,
        env,
    )
    return Path(result["package"])


def write_search_usage_record(env: dict[str, str], date: str, decision: str = "adapt") -> Path:
    codex_home = Path(env["CODEX_HOME"])
    record_dir = codex_home.parent / "artifacts" / "android-knowledge-intake" / "search-usage" / date.replace("-", "")
    record_dir.mkdir(parents=True, exist_ok=True)
    path = record_dir / f"{date.replace('-', '')}-search.json"
    path.write_text(
        json.dumps(
            {
                "schema": "android-knowledge-search-usage",
                "schema_version": "1",
                "created_at": f"{date}T09:30:00+08:00",
                "date": date,
                "profile": "member01",
                "member_alias": "member01",
                "query": "电源键 rk3576",
                "type": "all",
                "searched": True,
                "decision": decision,
                "reuse_decision": decision,
                "targets": ["case-power-key"],
                "match_points": ["同类电源键策略"],
                "mismatch_points": ["当前 Android 版本不同"],
                "reason": "需要适配当前项目源码路径",
                "outcome": "not_started",
                "result_count": 1,
                "results": [{"kind": "case", "id": "case-power-key", "title": "电源键策略"}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path



def create_framework_repo(root: Path) -> Path:
    source_root = root / "android-source"
    run(["git", "init", str(source_root)], root)
    run(["git", "config", "user.email", "framework@example.invalid"], source_root)
    run(["git", "config", "user.name", "Framework User"], source_root)
    source = source_root / "frameworks" / "base" / "packages" / "SystemUI" / "src" / "com" / "android" / "systemui" / "volume"
    source.mkdir(parents=True)
    java_file = source / "VolumeDialogImpl.java"
    java_file.write_text("class VolumeDialogImpl {}\n", encoding="utf-8")
    run(["git", "add", "."], source_root)
    run(["git", "commit", "-m", "initial"], source_root)
    java_file.write_text(
        "class VolumeDialogImpl {\n"
        "  //gyf 20260601@ adjust volume dialog position for product policy\n"
        "  static final String KEY = \"persist.sys.volume_dialog_position\";\n"
        "}\n",
        encoding="utf-8",
    )
    return source_root


class MemberAutomationFlowTests(unittest.TestCase):
    def test_member_facing_docs_preserve_repository_and_skill_boundaries(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in MEMBER_BOUNDARY_DOCS)
        forbidden = [
            "administrator review",
            "admin review",
            "管理员审核",
            "管理端审核",
            "等待管理员",
            "人工审核",
            "android-knowledge-curation ",
            "android-knowledge-curation\n",
            "提交到数据库仓库",
            "提交给数据库仓库",
            "提交数据库仓库",
        ]
        for term in forbidden:
            self.assertNotIn(term, combined)

        member_only_docs = (
            SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "SKILL.md",
            SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "config.example.toml",
            SETUP_PROMPT,
            SUITE_ROOT / "docs" / "skills" / "android-framework-ops" / "android-knowledge-intake" / "README.md",
        )
        member_text = "\n".join(path.read_text(encoding="utf-8") for path in member_only_docs)
        self.assertIn("server submission channel", member_text)
        self.assertIn("akbs-curation-maintainer", combined)
        self.assertIn("Weekly packages are progress archives only", member_text)
        self.assertIn("do not become knowledge materialization candidates", member_text)

    def test_member_setup_prompt_covers_current_plugin_and_endpoint(self) -> None:
        text = SETUP_PROMPT.read_text(encoding="utf-8")

        self.assertIn("首次启用提示词", text)
        self.assertIn("插件更新（plugin update）", text)
        self.assertIn("当前配置（current configuration）", text)
        self.assertIn("服务器上传入口（server upload endpoint）", text)
        self.assertIn("AKBS endpoint resolver", text)
        self.assertIn("doctor --strict --check-remote", text)

    def test_default_endpoint_targets_current_akbs_http_upload_api(self) -> None:
        module = load_intake_module()

        endpoint = module.resolve_akbs_endpoint({})

        self.assertEqual(endpoint["source"], "default")
        self.assertEqual(endpoint["submission_api_base_url"], "http://192.168.100.118:8088/akbs/api")
        self.assertNotIn("submission_method", endpoint)
        self.assertNotIn("submission_ssh_host", endpoint)
        self.assertNotIn("submission_command", endpoint)

    def test_http_submission_posts_tarball_to_current_akbs_upload_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "package"
            package_dir.mkdir()
            manifest = {
                "package_key": "20260705/member01/20260705-090000-daily",
                "package_kind": "daily_trace",
                "member_alias": "member01",
                "member_name": "成员甲",
                "run_id": "20260705-090000-daily",
                "date": "2026-07-05",
                "summary": "日报上传",
            }
            (package_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            (package_dir / "README.md").write_text("# 日报\n", encoding="utf-8")
            (package_dir / "local-check.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
            module = load_intake_module()
            requests = []

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(successful_upload_payload(), ensure_ascii=False).encode("utf-8")

            def fake_urlopen(request, timeout=0):
                requests.append((request, timeout))
                return FakeResponse()

            config = {
                "member_alias": "member01",
            }

            endpoint_env = {
                "CODEX_REPORT_AKBS_ENDPOINT_SUBMISSION_API_BASE_URL": "http://akbs.local/akbs/api",
                "CODEX_REPORT_AKBS_ENDPOINT_SUBMISSION_SESSION_COOKIE": "akbs_session=ignored",
                "CODEX_REPORT_AKBS_ENDPOINT_SUBMISSION_API_TOKEN": "ignored-token",
            }
            with patch.dict(os.environ, endpoint_env), patch("urllib.request.urlopen", fake_urlopen):
                result = module.server_submit_package(package_dir, config, "http")

            self.assertTrue(result["submitted"])
            self.assertEqual(len(requests), 1)
            request, timeout = requests[0]
            self.assertEqual(timeout, 30)
            self.assertEqual(request.full_url, "http://akbs.local/akbs/api/member/me/uploads/daily")
            self.assertEqual(request.get_header("Content-type"), "application/gzip")
            self.assertIsNone(request.get_header("Cookie"))
            self.assertEqual(request.get_header("X-akbs-user"), "member01")
            self.assertIsNone(request.get_header("X-akbs-token"))
            self.assertIsNone(request.get_header("X-akbs-role"))
            self.assertIsNone(request.get_header("X-forwarded-for"))
            self.assertIsNone(request.get_header("X-real-ip"))
            self.assertGreater(len(request.data), 0)

    def test_http_submission_preserves_declared_server_reason_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "package"
            package_dir.mkdir()
            (package_dir / "manifest.json").write_text(
                json.dumps({"package_kind": "daily_trace"}),
                encoding="utf-8",
            )
            module = load_intake_module()
            body = json.dumps(
                {
                    "schema": "akbs-error-envelope-v1",
                    "code": "package_already_exists",
                    "message": "package identity already exists with different content",
                    "request_id": "req_0123456789abcdef0123456789abcdef",
                    "detail": (
                        "incoming_contract_v1:package_already_exists: "
                        "package identity already exists with different content"
                    )
                }
            ).encode("utf-8")

            def fake_urlopen(request, timeout=0):
                raise urllib.error.HTTPError(request.full_url, 409, "Conflict", {}, io.BytesIO(body))

            with patch("urllib.request.urlopen", fake_urlopen):
                with self.assertRaises(SystemExit) as caught:
                    module.server_submit_package(package_dir, {"member_alias": "member01"}, "http")

            self.assertIn("HTTP 409", str(caught.exception))
            self.assertIn("code=package_already_exists", str(caught.exception))
            self.assertIn("request_id=req_0123456789abcdef0123456789abcdef", str(caught.exception))

    def test_missing_alias_stops_before_packaging_or_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp) / "package"
            package_dir.mkdir()
            (package_dir / "manifest.json").write_text(
                json.dumps({"package_kind": "daily_trace"}),
                encoding="utf-8",
            )
            module = load_intake_module()

            with patch(
                "akbs_intake.submit.package_tar_gz_bytes",
            ) as pack, patch("urllib.request.urlopen") as urlopen:
                with self.assertRaises(SystemExit) as caught:
                    module.server_submit_package(package_dir, {"member_alias": ""}, "http")

            self.assertIn("member_alias", str(caught.exception))
            pack.assert_not_called()
            urlopen.assert_not_called()

    def test_http_submission_timeout_does_not_fallback_to_ssh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "package"
            package_dir.mkdir()
            manifest = {
                "package_key": "20260705/member01/20260705-091500-daily",
                "package_kind": "daily_trace",
                "member_alias": "member01",
                "member_name": "成员甲",
                "run_id": "20260705-091500-daily",
                "date": "2026-07-05",
                "summary": "日报上传",
            }
            (package_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            (package_dir / "README.md").write_text("# 日报\n", encoding="utf-8")
            module = load_intake_module()

            def fake_urlopen(request, timeout=0):
                raise TimeoutError("timed out")

            def forbidden_subprocess_run(*args, **kwargs):
                raise AssertionError("HTTP upload must not fallback to ssh/local subprocess submission")

            with patch("urllib.request.urlopen", fake_urlopen), patch(
                "subprocess.run",
                forbidden_subprocess_run,
            ):
                with self.assertRaises(SystemExit) as caught:
                    module.server_submit_package(package_dir, {"member_alias": "member01"}, "http")

            self.assertIn("HTTP 上传入口提交失败", str(caught.exception))
            self.assertIn("code=transport_unavailable", str(caught.exception))
            self.assertIn("kind=retryable", str(caught.exception))
            self.assertNotIn("timed out", str(caught.exception))
            self.assertNotIn("token", str(caught.exception).lower())

    def test_doctor_reports_fixed_ip_identity_and_ignores_residual_token(self) -> None:
        module = load_intake_module()
        config = {
            "out_dir": "$CODEX_HOME/artifacts/android-knowledge-intake",
            "role": "member",
            "allowed_modes": "daily,weekly,patch",
            "member_alias": "member01",
            "member_name": "成员甲",
        }

        with patch.dict(
            os.environ,
            {"CODEX_REPORT_AKBS_ENDPOINT_SUBMISSION_API_TOKEN": "ignored-token"},
        ):
            result = module.doctor(config, [])

        rendered = json.dumps(result, ensure_ascii=False)
        self.assertEqual(result["member_identity"]["mode"], "fixed_ip_alias")
        self.assertEqual(result["member_identity"]["status"], "ready")
        self.assertNotIn("ignored-token", rendered)
        self.assertNotIn("upload_token", result)
        self.assertNotIn("submission_api_token", result["akbs_endpoint"])

    def test_ssh_submission_method_is_rejected_before_any_upload_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package_dir = root / "package"
            package_dir.mkdir()
            (package_dir / "manifest.json").write_text(
                json.dumps({"package_kind": "daily_trace"}, ensure_ascii=False),
                encoding="utf-8",
            )
            module = load_intake_module()

            with patch("urllib.request.urlopen") as urlopen:
                with self.assertRaises(SystemExit) as caught:
                    module.server_submit_package(package_dir, {"member_alias": "member01"}, "ssh")

            self.assertFalse(urlopen.called)
            self.assertIn("只支持 HTTP API", str(caught.exception))

    def test_http_upload_type_uses_three_current_package_routes(self) -> None:
        module = load_intake_module()

        self.assertEqual(module.upload_type_for_manifest({"package_kind": "daily_trace"}), "daily")
        self.assertEqual(module.upload_type_for_manifest({"package_kind": "weekly_trace"}), "weekly")
        self.assertEqual(module.upload_type_for_manifest({"package_kind": "framework_change"}), "patch")
        with self.assertRaises(SystemExit) as retired:
            module.upload_type_for_manifest(
                {
                    "package_kind": "framework_change",
                    "supplement_for_package_key": "20260705/wick/20260705-091500-patch",
                },
            )
        self.assertIn("legacy_patch_contract_not_supported", str(retired.exception))
        with self.assertRaises(SystemExit):
            module.upload_type_for_manifest({"package_kind": "unknown"})

    def test_plugin_freshness_detects_checkout_behind_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = seed_stale_plugin_checkout(root)
            module = load_intake_module()
            module.PLUGIN_ROOT = plugin_root

            result = module.plugin_freshness_check(fetch=True)

            self.assertEqual(result["status"], "UPDATED_RESTART_REQUIRED")
            self.assertTrue(result["blocking"])
            self.assertEqual(result["auto_update"]["status"], "PASS")
            self.assertIn("不能热刷新", result["message"])
            self.assertIn("git -C", result["update_command"])
            self.assertIn("pull --ff-only", result["update_command"])

    def test_plugin_freshness_non_git_install_is_nonblocking_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = root / "codex-plugin-cache" / "android-knowledge-intake"
            plugin_root.mkdir(parents=True)
            module = load_intake_module()
            module.PLUGIN_ROOT = plugin_root

            result = module.plugin_freshness_check(fetch=True)
            forced = module.plugin_freshness_check(fetch=True, require=True)

            self.assertEqual(result["status"], "UNKNOWN")
            self.assertFalse(result["blocking"])
            self.assertEqual(forced["status"], "UNKNOWN")
            self.assertTrue(forced["blocking"])

    def test_packaged_plugin_freshness_auto_installs_newer_marketplace_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = seed_packaged_plugin_install(root, version="1.0.24")
            module = load_intake_module()
            module.PLUGIN_ROOT = plugin_root
            module.fetch_remote_plugin_manifest = lambda metadata: {"version": "1.0.26"}
            calls: list[list[str]] = []

            def fake_run(cmd: list[str], check: bool = False, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
                calls.append(cmd)
                if cmd[:4] == ["git", "-C", str(plugin_root), "rev-parse"]:
                    return subprocess.CompletedProcess(cmd, 1, "", "not a git repository")
                if cmd[:4] == ["codex", "plugin", "marketplace", "upgrade"]:
                    return subprocess.CompletedProcess(cmd, 0, json.dumps({"upgraded": True}), "")
                if cmd[:3] == ["codex", "plugin", "add"]:
                    return subprocess.CompletedProcess(cmd, 0, json.dumps({"installed": True, "version": "1.0.26"}), "")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            module.run = fake_run
            old_env = os.environ.copy()
            try:
                os.environ["CODEX_HOME"] = str(root / "empty-codex-home")

                result = module.plugin_freshness_check(fetch=True)

                self.assertEqual(result["status"], "UPDATED_RESTART_REQUIRED")
                self.assertTrue(result["blocking"])
                self.assertEqual(result["local_version"], "1.0.24")
                self.assertEqual(result["remote_version"], "1.0.26")
                self.assertEqual(result["auto_update"]["status"], "PASS")
                self.assertIn(
                    ["codex", "plugin", "marketplace", "upgrade", "android-framework-codex-suite", "--json"],
                    calls,
                )
                self.assertIn(["codex", "plugin", "add", "android-framework-ops@android-framework-codex-suite", "--json"], calls)
                self.assertIn("当前会话不能热刷新", result["message"])
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_packaged_plugin_freshness_blocks_old_session_cache_after_install_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_home = root / "codex-home"
            plugin_root = seed_packaged_plugin_install(root, version="1.0.24")
            seed_codex_plugin_cache(codex_home, "1.0.26")
            module = load_intake_module()
            module.PLUGIN_ROOT = plugin_root
            module.fetch_remote_plugin_manifest = lambda metadata: {"version": "1.0.26"}
            old_env = os.environ.copy()
            try:
                os.environ["CODEX_HOME"] = str(codex_home)

                result = module.plugin_freshness_check(fetch=True, require=True)

                self.assertEqual(result["status"], "SESSION_CACHE_STALE")
                self.assertTrue(result["blocking"])
                self.assertEqual(result["local_version"], "1.0.24")
                self.assertEqual(result["installed_plugin_version"], "1.0.26")
                self.assertEqual(result["skill_cache_version"], "1.0.24")
                self.assertIn("当前会话不能热刷新技能", result["message"])
            finally:
                os.environ.clear()
                os.environ.update(old_env)

    def test_member_generation_reexecs_new_packaged_skill_after_auto_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote)
            env.pop("CODEX_REPORT_SKIP_PLUGIN_UPDATE_CHECK", None)
            skill_root = seed_codex_plugin_cache(Path(env["CODEX_HOME"]), "1.0.26")
            script_path = skill_root / "scripts" / "android_knowledge_intake.py"
            script_path.parent.mkdir(parents=True)
            script_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
            plugin_root = skill_root.parents[1]
            module = load_intake_module()
            module.plugin_version_gate_check = lambda config, fetch=True, require=True: {
                "status": "UPDATED_RESTART_REQUIRED",
                "blocking": True,
                "plugin_name": "android-framework-ops",
                "local_version": "1.0.24",
                "remote_version": "1.0.26",
                "auto_update": {
                    "status": "PASS",
                    "installed_plugin_path": str(plugin_root),
                    "installed_plugin_version": "1.0.26",
                },
                "message": "插件已自动更新。",
            }
            exec_calls: list[tuple[str, list[str]]] = []

            def fake_execv(executable: str, args: list[str]) -> None:
                exec_calls.append((executable, args))
                raise RuntimeError("execv called")

            old_argv = sys.argv[:]
            old_env = os.environ.copy()
            try:
                os.environ.clear()
                os.environ.update(env)
                sys.argv = [
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "daily",
                    "--date",
                    "2026-06-01",
                    "--run-id",
                    "20260601-210000-daily",
                    "--prepare",
                ]
                with patch("os.execv", fake_execv):
                    with self.assertRaisesRegex(RuntimeError, "execv called"):
                        module.main()

                self.assertEqual(len(exec_calls), 1)
                executable, args = exec_calls[0]
                self.assertEqual(executable, sys.executable)
                self.assertEqual(args[0], sys.executable)
                self.assertEqual(args[1], str(script_path))
                self.assertEqual(args[2:], sys.argv[1:])
                self.assertEqual(os.environ["CODEX_REPORT_PLUGIN_REEXEC_ATTEMPTED"], "1")
            finally:
                sys.argv = old_argv
                os.environ.clear()
                os.environ.update(old_env)

    def test_source_metadata_records_packaged_plugin_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = seed_packaged_plugin_install(root, version="1.0.24")
            module = load_intake_module()
            module.PLUGIN_ROOT = plugin_root
            module.LAST_PLUGIN_VERSION_GATE = {
                "status": "PASS",
                "result": "PASS",
                "blocking": False,
                "plugin_version": "1.0.24",
                "installed_plugin_version": "1.0.24",
                "remote_plugin_version": "1.0.24",
                "skill_cache_version": "1.0.24",
                "skill_cache_path": str(plugin_root),
                "checked_at": "2026-06-30T10:00:00+08:00",
                "message": "test gate",
            }

            source = module.source_metadata({"member_alias": "member01"}, "android-knowledge-intake")

            self.assertEqual(source["plugin_name"], "android-framework-ops")
            self.assertEqual(source["plugin_version"], "1.0.24")
            self.assertEqual(source["skill_version"], "1.0.24")
            self.assertEqual(source["plugin_installation"], "packaged")
            self.assertEqual(source["installed_plugin_version"], "1.0.24")
            self.assertEqual(source["remote_plugin_version"], "1.0.24")
            self.assertEqual(source["skill_cache_version"], "1.0.24")
            self.assertEqual(source["plugin_version_check"]["result"], "PASS")
            self.assertEqual(source["plugin_version_check"]["checked_at"], "2026-06-30T10:00:00+08:00")

    def test_member_generation_modes_stop_when_plugin_checkout_is_stale(self) -> None:
        for mode in ("daily", "weekly", "patch"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                remote = seed_knowledge_remote(root)
                plugin_root = seed_stale_plugin_checkout(root)
                env = write_member_config(root, remote)
                env.pop("CODEX_REPORT_SKIP_PLUGIN_UPDATE_CHECK", None)
                module = load_intake_module()
                old_argv = sys.argv[:]
                old_env = os.environ.copy()
                try:
                    module.PLUGIN_ROOT = plugin_root
                    os.environ.clear()
                    os.environ.update(env)
                    with self.subTest(mode=mode):
                        sys.argv = [
                            str(INTAKE_SCRIPT),
                            "--profile",
                            "member01",
                            mode,
                            "--date",
                            "2026-06-01",
                            "--run-id",
                            f"20260601-210000-{mode}",
                            "--prepare",
                        ]
                        stdout = io.StringIO()

                        with patch("os.execv") as execv, contextlib.redirect_stdout(stdout):
                            code = module.main()

                        self.assertFalse(execv.called)
                        self.assertEqual(code, 1)
                        payload = json.loads(stdout.getvalue())
                        self.assertEqual(payload["status"], "FAIL")
                        self.assertEqual(payload["plugin_freshness"]["status"], "UPDATED_RESTART_REQUIRED")
                        self.assertEqual(payload["plugin_freshness"]["auto_update"]["status"], "PASS")
                        self.assertIn("不能热刷新", payload["message"])
                finally:
                    sys.argv = old_argv
                    os.environ.clear()
                    os.environ.update(old_env)

    def test_member_generation_requires_confirmed_latest_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            clone_member_knowledge_worktree(root, remote)
            env = write_member_config(root, remote)
            env.pop("CODEX_REPORT_SKIP_PLUGIN_UPDATE_CHECK", None)
            module = load_intake_module()
            calls: list[tuple[bool, bool]] = []

            def unknown_freshness(config: dict[str, str] | None = None, fetch: bool = True, require: bool = False) -> dict:
                calls.append((fetch, require))
                return {
                    "status": "UNKNOWN",
                    "blocking": require,
                    "message": "无法确认插件是否为最新版本。",
                }

            module.plugin_version_gate_check = unknown_freshness
            old_argv = sys.argv[:]
            old_env = os.environ.copy()
            try:
                os.environ.clear()
                os.environ.update(env)
                sys.argv = [
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "daily",
                    "--date",
                    "2026-06-01",
                    "--run-id",
                    "20260601-210000-daily",
                    "--prepare",
                ]
                stdout = io.StringIO()

                with contextlib.redirect_stdout(stdout):
                    code = module.main()

                self.assertEqual(code, 1)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["status"], "FAIL")
                self.assertEqual(payload["plugin_freshness"]["status"], "UNKNOWN")
                self.assertTrue(payload["plugin_freshness"]["blocking"])
                self.assertIn((True, True), calls)
            finally:
                sys.argv = old_argv
                os.environ.clear()
                os.environ.update(old_env)

    def test_current_submission_and_knowledge_config_doctor_uses_member_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote)
            config_text = (Path(env["CODEX_HOME"]) / "report" / "config.toml").read_text(encoding="utf-8")

            result = run_json(
                [sys.executable, str(INTAKE_SCRIPT), "--profile", "member01", "doctor"],
                SUITE_ROOT,
                env,
            )

            self.assertNotIn("[submission]", config_text)
            self.assertNotIn("[knowledge]", config_text)
            self.assertNotIn("server_profile", config_text)
            self.assertEqual(result["akbs_endpoint"]["source"], "default")
            self.assertNotIn("submission_method", result)
            self.assertNotIn("submission_command", result)
            self.assertNotIn("database_repo_worktree", result)
            self.assertIn("worktrees/knowledge", result["knowledge_repo_worktree"])
            self.assertNotIn("submission_repo_url", result)
            self.assertNotIn("approved_repo_url", result)

    def test_daily_uses_remote_project_anchor_and_filters_codex_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote, synthetic_data=False)
            codex_home = Path(env["CODEX_HOME"])
            source_root = create_framework_repo(root)
            run(["git", "checkout", "-b", "TVA10A2R_camera_fix"], source_root)
            noise_dir = root / "codex-home" / "worktrees" / "knowledge-guiliu"
            noise_dir.mkdir(parents=True)

            write_codex_session(
                codex_home,
                "22222222-2222-3333-4444-555555555555",
                source_root,
                dt.date(2026, 6, 3),
                [
                    "今天通过 ssh test35 连接服务器，在 /home/jinny/work/rk/TVA10A2R 源码里处理 TVA10A2R 视频通话看不到设备端画面，dual_camera_error 补丁已改完，进度80%，待设备验证。",
                    "继续排查 TVA10A2R 视频监控画面旋转问题，进度40%。",
                ],
                thread_name="TVA10A2R 视频通话和视频监控定制",
                commands=[
                    "ssh test35",
                    "cd /home/jinny/work/rk/TVA10A2R && git branch --show-current",
                    "git diff frameworks/base hardware/rockchip/camera",
                ],
            )
            write_codex_session(
                codex_home,
                "33333333-2222-3333-4444-555555555555",
                noise_dir,
                dt.date(2026, 6, 3),
                [
                    "Enter passphrase for key 是123",
                    "The following is the Codex agent history added since your last approval assessment.",
                    "# Files mentioned by the user: screenshot.jpg",
                ],
                thread_name="The following is the Codex agent history whose request action you are assessing",
            )

            package = prepare_daily_package(env, "2026-06-03", "20260603-210000-daily")
            report = read_package_report(package)
            findings = read_package_findings(package)
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            project_inference = json.loads((package / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))
            finding_text = json.dumps(findings, ensure_ascii=False)

            self.assertEqual(manifest["project"], "TVA10A2R")
            self.assertIn("materials/evidence/project_inference.json", manifest["files"]["evidence"])
            self.assertEqual(project_inference["payload"]["project"], "TVA10A2R")
            self.assertIn("日报上下文", " ".join(project_inference["payload"]["basis"]))
            self.assertIn("### **TVA10A2R**", report)
            self.assertIn("视频通话", report)
            self.assertIn("视频监控", report)
            self.assertIn("待设备验证", report)
            self.assertNotIn("TVA10A2R_camera_fix", report)
            self.assertNotIn("knowledge-guiliu", report)
            self.assertNotIn("Enter passphrase", report)
            self.assertNotIn("Codex agent history", report)
            self.assertNotIn("files-mentioned", report)
            self.assertIn("TVA10A2R", finding_text)
            self.assertNotIn("Enter passphrase", finding_text)

    def test_daily_validation_requires_project_inference_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote, synthetic_data=False)
            codex_home = Path(env["CODEX_HOME"])
            source_root = create_framework_repo(root)
            write_codex_session(
                codex_home,
                "55555555-2222-3333-4444-555555555555",
                source_root,
                dt.date(2026, 6, 3),
                "今天处理 TVA10A2R 状态栏策略，进度60%。",
                thread_name="TVA10A2R 状态栏策略",
            )
            package = prepare_daily_package(env, "2026-06-03", "20260603-212000-daily")
            manifest_path = package / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"]["evidence"] = [
                rel for rel in manifest["files"]["evidence"] if rel != "materials/evidence/project_inference.json"
            ]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            module = load_intake_module()

            check = module.validate_package(package)

            self.assertEqual(check["status"], "FAIL")
            self.assertIn("daily_trace 缺少 project_inference evidence", check["errors"])

    def test_daily_package_carries_member_search_usage_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote)
            write_search_usage_record(env, "2026-06-01", decision="adapt")

            package = prepare_daily_package(env, "2026-06-01", "20260601-210000-daily")

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("materials/evidence/search_before_change.json", manifest["files"]["evidence"])
            evidence = json.loads((package / "materials" / "evidence" / "search_before_change.json").read_text(encoding="utf-8"))
            payload = evidence["payload"]
            self.assertTrue(payload["searched"])
            self.assertEqual(payload["reuse_decision"], "adapt")
            self.assertEqual(payload["queries"], ["电源键 rk3576"])
            self.assertEqual(payload["targets"], ["case-power-key"])

    def test_daily_splits_project_code_from_trailing_description(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote, synthetic_data=False)
            codex_home = Path(env["CODEX_HOME"])
            source_root = create_framework_repo(root)
            run(["git", "checkout", "-b", "android16"], source_root)

            write_codex_session(
                codex_home,
                "44444444-2222-3333-4444-555555555555",
                source_root,
                dt.date(2026, 6, 3),
                "今日完成 TVE1086U整体项目交接，整理运营商文档和 apply 脚本注意事项，进度100%。",
                thread_name="TVE1086U整体项目交接",
            )

            package = prepare_daily_package(env, "2026-06-03", "20260603-211000-daily")
            report = read_package_report(package)
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "TVE1086U")
            self.assertIn("### **TVE1086U**", report)
            self.assertIn("整体项目交接", report)
            self.assertNotIn("### **TVE1086U**整体项目交接", report)
            self.assertNotIn("### android16", report)

    def test_report_project_customer_phrase_allows_daily_and_weekly_local_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote, synthetic_data=False)
            codex_home = Path(env["CODEX_HOME"])
            source_root = create_framework_repo(root)

            write_codex_session(
                codex_home,
                "44444444-3333-3333-4444-555555555555",
                source_root,
                dt.date(2026, 6, 3),
                [
                    "TVE1086U 青鸾云，帮我生成日报并提交。",
                    "今天处理 TVE1086U 状态栏策略，进度100%。",
                ],
                thread_name="TVE1086U 日报",
            )

            daily = prepare_daily_package(env, "2026-06-03", "20260603-213000-daily")
            weekly = prepare_weekly_package(env, "2026-06-03", "20260603-223000-weekly")
            daily_check = json.loads((daily / "local-check.json").read_text(encoding="utf-8"))
            weekly_check = json.loads((weekly / "local-check.json").read_text(encoding="utf-8"))
            daily_view = read_report_view(daily)
            weekly_view = read_report_view(weekly)
            project_inference = json.loads((daily / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))

            self.assertEqual(daily_check["status"], "PASS")
            self.assertEqual(weekly_check["status"], "FAIL")
            self.assertIn("TVE1086U.project_role", "\n".join(weekly_check["errors"]))
            self.assertIn("TVE1086U.requirement_date", "\n".join(weekly_check["errors"]))
            self.assertIn("TVE1086U.requirement_source", "\n".join(weekly_check["errors"]))
            self.assertEqual(daily_view["payload"]["projects"][0]["project"], "TVE1086U")
            self.assertEqual(daily_view["payload"]["projects"][0]["customer"], "青鸾云")
            self.assertEqual(weekly_view["payload"]["projects"][0]["project"], "TVE1086U")
            self.assertEqual(weekly_view["payload"]["projects"][0]["customer"], "青鸾云")
            self.assertEqual(project_inference["payload"]["customer_name"], "青鸾云")

    def test_report_customer_hierarchy_is_preserved_in_daily_and_weekly_views(self) -> None:
        load_intake_module()
        sessions_module = importlib.import_module("akbs_intake.report_sessions")
        validation_module = importlib.import_module("akbs_intake.reports.validation")
        self.assertEqual(
            sessions_module.project_customer_contexts_from_text("TVE1086U 青鸾云"),
            [("TVE1086U", {"customer_name": "青鸾云"})],
        )
        self.assertEqual(
            sessions_module.project_customer_contexts_from_text("TVE1067M1 韩福友 P"),
            [("TVE1067M1", {"customer_name": "韩福友", "downstream_customer": "P"})],
        )
        self.assertEqual(
            validation_module.report_project_customer_errors(
                "report_view.json",
                [{"project": "TVE1086U", "customer": "青鸾云"}],
                "projects",
            ),
            [],
        )
        self.assertTrue(
            validation_module.report_project_customer_errors(
                "report_view.json",
                [{"project": "TVE1086U", "customer": "日报"}],
                "projects",
            )
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote, synthetic_data=False)
            codex_home = Path(env["CODEX_HOME"])
            source_root = create_framework_repo(root)
            write_codex_session(
                codex_home,
                "44444444-3434-3333-4444-555555555555",
                source_root,
                dt.date(2026, 6, 3),
                [
                    "TVE1091U AOC 福建移动高清，帮我生成日报并提交。",
                    "今天完成 TVE1091U 权限策略修改，进度100%。",
                ],
                thread_name="TVE1091U 日报",
            )

            daily = prepare_daily_package(env, "2026-06-03", "20260603-214500-daily")
            daily_check = json.loads((daily / "local-check.json").read_text(encoding="utf-8"))
            daily_report = read_package_report(daily)
            daily_view = read_report_view(daily)["payload"]
            project_inference = json.loads(
                (daily / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8")
            )["payload"]

            self.assertEqual(daily_check["status"], "PASS")
            self.assertIn("### **TVE1091U** AOC 福建移动高清", daily_report)
            self.assertEqual(daily_view["material_name"], "TVE1091U（AOC → 福建移动高清）")
            self.assertEqual(daily_view["projects"][0]["customer"], "AOC")
            self.assertEqual(daily_view["projects"][0]["downstream_customer"], "福建移动高清")
            self.assertEqual(project_inference["customer_name"], "AOC")
            self.assertEqual(project_inference["downstream_customer"], "福建移动高清")

            facts = write_weekly_facts(root / "artifacts" / "customer-hierarchy-weekly-facts.json")
            facts_payload = json.loads(facts.read_text(encoding="utf-8"))
            facts_payload["projects"][0]["project"] = "TVE1091U"
            facts_payload["projects"][0]["customer"] = "AOC"
            facts_payload["projects"][0]["downstream_customer"] = "福建移动高清"
            facts.write_text(json.dumps(facts_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            weekly = prepare_weekly_package(env, "2026-06-03", "20260603-224500-weekly", facts)
            weekly_check = json.loads((weekly / "local-check.json").read_text(encoding="utf-8"))
            weekly_report = read_package_report(weekly, "weekly")
            weekly_view = read_report_view(weekly)["payload"]

            self.assertEqual(weekly_check["status"], "PASS")
            self.assertIn("### **TVE1091U** AOC 福建移动高清", weekly_report)
            self.assertEqual(weekly_view["material_name"], "TVE1091U（AOC → 福建移动高清）")
            self.assertEqual(weekly_view["projects"][0]["customer"], "AOC")
            self.assertEqual(weekly_view["projects"][0]["downstream_customer"], "福建移动高清")

    def test_weekly_explicit_project_facts_render_exact_template_and_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote, synthetic_data=False)
            codex_home = Path(env["CODEX_HOME"])
            source_root = create_framework_repo(root)
            write_codex_session(
                codex_home,
                "55555555-3333-3333-4444-555555555555",
                source_root,
                dt.date(2026, 6, 3),
                "TVE1086U 青鸾云，本周完成状态栏策略修改和设备验证。",
            )
            facts = write_weekly_facts(root / "artifacts" / "weekly-facts.json")

            weekly = prepare_weekly_package(env, "2026-06-03", "20260603-225000-weekly", facts)
            check = json.loads((weekly / "local-check.json").read_text(encoding="utf-8"))
            report = read_package_report(weekly, "weekly")
            view = read_report_view(weekly)["payload"]["projects"][0]
            fact_sources = json.loads(
                (weekly / "materials" / "evidence" / "weekly_fact_sources.json").read_text(encoding="utf-8")
            )

            self.assertEqual(check["status"], "PASS")
            self.assertIn("本周完成状态栏策略修改和设备验证。", report)
            self.assertNotIn("本周围绕 **TVE1086U** 青鸾云 项目推进：下周继续", report)
            self.assertIn("- 项目角色：主责", report)
            self.assertIn("- 需求时间：2026-05-18", report)
            self.assertIn("- 需求来源：CR", report)
            self.assertIn("- 共 12 项：需求 5、移植 3、Bug 3、BSP 1", report)
            self.assertIn("- 本周完成 3 项：需求 1、移植 1、Bug 1", report)
            self.assertIn("- 当前剩余 3 项：需求 1、移植 1、BSP 1", report)
            self.assertIn("#### 3. 重点说明", report)
            self.assertIn("#### 4. 风险 / 依赖", report)
            self.assertEqual(view["requirement_structure"], "共 12 项：需求 5、移植 3、Bug 3、BSP 1")
            self.assertEqual(view["completed_this_week"], "本周完成 3 项：需求 1、移植 1、Bug 1")
            self.assertEqual(view["remaining"], "当前剩余 3 项：需求 1、移植 1、BSP 1")
            self.assertEqual(fact_sources["payload"]["source"], "explicit_weekly_facts")
            self.assertEqual(fact_sources["payload"]["missing_fields"], [])

    def test_weekly_demand_migration_and_bug_are_separate_and_bsp_cannot_be_completed(self) -> None:
        load_intake_module()
        weekly_module = importlib.import_module("akbs_intake.reports.weekly_facts")

        self.assertEqual(
            weekly_module.normalize_counts("39 项：移植 24、Bug 15"),
            {"demand": 0, "migration": 24, "bug": 15, "bsp": 0},
        )
        self.assertEqual(
            weekly_module.normalize_counts({"feature_port": 4, "bug": 14, "bsp": 0}),
            {"demand": 0, "migration": 4, "bug": 14, "bsp": 0},
        )
        self.assertEqual(weekly_module.item_category("完成客户功能补丁移植", completed=True), "migration")
        self.assertEqual(weekly_module.item_category("完成壁纸崩溃修复移植", completed=True), "bug")
        self.assertEqual(weekly_module.item_category("等待 BSP 提供新固件"), "bsp")
        self.assertEqual(weekly_module.item_category("完成 BSP 联调", completed=True), "demand")

        render_module = importlib.import_module("akbs_intake.reports.render")
        self.assertEqual(
            render_module.project_ledger_totals(
                [
                    ("等待 BSP 修复驱动问题", "进行中"),
                    ("完成 BSP 联调", "已完成"),
                    ("完成壁纸崩溃修复移植", "已完成"),
                ]
            ),
            {"demand": 1, "migration": 0, "bug": 1, "bsp": 1, "other": 0, "total": 3},
        )

        with tempfile.TemporaryDirectory() as tmp:
            facts = write_weekly_facts(Path(tmp) / "weekly-facts.json")
            payload = json.loads(facts.read_text(encoding="utf-8"))
            payload["projects"][0]["completed_this_week"]["bsp"] = 1
            facts.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "completed_this_week.bsp 必须为 0"):
                weekly_module.load_explicit_facts(facts, "20260601-20260607")

            payload["projects"][0]["completed_this_week"]["bsp"] = "0"
            facts.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "completed_this_week 计数必须是非负整数"):
                weekly_module.load_explicit_facts(facts, "20260601-20260607")

    def test_weekly_collaborator_may_omit_project_total(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote, synthetic_data=False)
            codex_home = Path(env["CODEX_HOME"])
            source_root = create_framework_repo(root)
            write_codex_session(
                codex_home,
                "55555555-3333-3333-4444-555555555556",
                source_root,
                dt.date(2026, 6, 3),
                "TVE1086U 青鸾云，本周协作完成状态栏策略修改。",
            )
            facts = write_weekly_facts(root / "artifacts" / "collaborator-weekly-facts.json")
            payload = json.loads(facts.read_text(encoding="utf-8"))
            payload["projects"][0]["project_role"] = "协作"
            payload["projects"][0].pop("requirement_structure")
            facts.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            weekly = prepare_weekly_package(env, "2026-06-03", "20260603-225100-weekly", facts)
            report = read_package_report(weekly, "weekly")
            view = read_report_view(weekly)["payload"]["projects"][0]

            self.assertEqual(json.loads((weekly / "local-check.json").read_text(encoding="utf-8"))["status"], "PASS")
            self.assertIn("- 项目角色：协作", report)
            self.assertNotIn("- 共 12 项", report)
            self.assertNotIn("requirement_structure", view)

    def test_weekly_main_total_source_and_legacy_category_are_hard_gates(self) -> None:
        load_intake_module()
        weekly_module = importlib.import_module("akbs_intake.reports.weekly_facts")
        with tempfile.TemporaryDirectory() as tmp:
            facts = write_weekly_facts(Path(tmp) / "weekly-facts.json")
            payload = json.loads(facts.read_text(encoding="utf-8"))

            payload["projects"][0].pop("requirement_structure")
            facts.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "requirement_structure 主责必须提供"):
                weekly_module.load_explicit_facts(facts, "20260601-20260607")

            payload = json.loads(write_weekly_facts(facts).read_text(encoding="utf-8"))
            payload["projects"][0]["requirement_source"] = "客户需求文档"
            facts.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "requirement_source 只能是 CR、TL、PM、TE 或 BSP"):
                weekly_module.load_explicit_facts(facts, "20260601-20260607")

            payload = json.loads(write_weekly_facts(facts).read_text(encoding="utf-8"))
            payload["projects"][0]["requirement_date"] = "20260518"
            facts.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "requirement_date 必须是 YYYY-MM-DD"):
                weekly_module.load_explicit_facts(facts, "20260601-20260607")

            payload = json.loads(write_weekly_facts(facts).read_text(encoding="utf-8"))
            payload["projects"][0]["requirement_structure"] = {"custom": 8, "bug": 3}
            facts.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "定制不能自动拆分"):
                weekly_module.load_explicit_facts(facts, "20260601-20260607")

            payload["schema"] = "akbs-weekly-project-facts-v1"
            facts.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "不能自动拆成需求和移植"):
                weekly_module.load_explicit_facts(facts, "20260601-20260607")

    def test_weekly_completed_plus_remaining_cannot_exceed_main_total(self) -> None:
        load_intake_module()
        weekly_module = importlib.import_module("akbs_intake.reports.weekly_facts")
        with tempfile.TemporaryDirectory() as tmp:
            facts = write_weekly_facts(Path(tmp) / "weekly-facts.json")
            payload = json.loads(facts.read_text(encoding="utf-8"))
            payload["projects"][0]["requirement_structure"]["demand"] = 1
            payload["projects"][0]["completed_this_week"]["demand"] = 1
            payload["projects"][0]["remaining"]["demand"] = 1
            facts.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "本周完成加当前剩余不能超过项目总量"):
                weekly_module.load_explicit_facts(facts, "20260601-20260607")

    def test_weekly_cross_day_session_uses_target_date_messages_and_assistant_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = load_intake_module()
            codex_home = root / "codex-home"
            source_root = create_framework_repo(root)
            session_dir = codex_home / "sessions" / "2026" / "05" / "31"
            session_dir.mkdir(parents=True)
            session_path = session_dir / "66666666-3333-3333-4444-555555555555.jsonl"
            rows = [
                {
                    "timestamp": "2026-05-31T20:00:00+08:00",
                    "type": "session_meta",
                    "payload": {"id": "66666666-3333-3333-4444-555555555555", "cwd": str(source_root)},
                },
                {
                    "timestamp": "2026-06-01T10:00:00+08:00",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "TVE1086U 青鸾云，处理状态栏策略。"}],
                    },
                },
                {
                    "timestamp": "2026-06-01T18:00:00+08:00",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "TVE1086U 状态栏策略已完成并验证通过。"}],
                    },
                },
            ]
            session_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
            dates = {dt.date(2026, 6, 1)}
            config = {"codex_home": str(codex_home), "timezone": "Asia/Shanghai"}
            module.configure_report_session_consent(
                config,
                dates,
                granted=True,
                fields=["work_summary", "project_hint"],
            )

            sessions = module.parse_sessions(config, dates)
            items = module.items_by_project(sessions, [])

            self.assertEqual(len(sessions), 1)
            self.assertIn("已完成并验证通过", sessions[0].outcomes[0])
            self.assertEqual(items["TVE1086U"][0][1], "已完成")

    def test_weekly_history_uses_current_akbs_daily_and_previous_week_ledger(self) -> None:
        load_intake_module()
        weekly_module = importlib.import_module("akbs_intake.reports.weekly_facts")
        previous = {
            "package_key": "20260607/member01/current-weekly",
            "package_kind": "weekly_trace",
            "week_range": "20260601-20260607",
            "standard_view": {
                "projects": [
                    {
                        "project": "TVE1086U",
                        "customer": "青鸾云",
                        "project_role": "主责",
                        "week_summary": "上周持续推进状态栏和亮度事项。",
                        "requirement_date": "2026-05-18",
                        "requirement_source": "CR",
                        "requirement_structure": "共 3 项：需求 1、移植 1、Bug 1",
                        "completed_this_week": "本周完成 1 项：移植 1",
                        "remaining": "当前剩余 2 项：需求 1、Bug 1",
                        "completed_items": ["完成基础接口适配"],
                        "remaining_items": ["状态栏策略修改", "修复亮度同步问题"],
                        "key_points": ["无"],
                        "risks": ["无超过 3 天无进展事项。"],
                        "dependencies": ["无外部依赖事项。"],
                        "next_week_plan": ["完成状态栏和亮度问题收敛"],
                    }
                ]
            },
        }
        daily = {
            "package_key": "20260610/member01/current-daily",
            "package_kind": "daily_trace",
            "report_date": "2026-06-10",
            "standard_view": {
                "projects": [
                    {
                        "project": "TVE1086U",
                        "customer": "青鸾云",
                        "work_items": [
                            {"name": "状态栏策略修改", "result": "已完成并验证通过"},
                            {"name": "新增开关功能", "result": "已完成"},
                            {"name": "修复亮度同步问题", "result": "处理中"},
                        ],
                        "tomorrow_focus": ["完成亮度同步问题回归"],
                    }
                ]
            },
        }

        def fake_fetch(_config: dict[str, str], package_kind: str, _month: str) -> list[dict]:
            return [daily] if package_kind == "daily_trace" else [previous]

        config = {
            "member_alias": "member01",
            "submission_api_base_url": "http://127.0.0.1:1/akbs/api",
            "weekly_history_api_enabled": "true",
        }
        with patch.object(weekly_module, "fetch_current_report_items", side_effect=fake_fetch):
            result = weekly_module.build_weekly_facts(
                config,
                dt.date(2026, 6, 8),
                dt.date(2026, 6, 14),
                "20260608-20260614",
            )

        row = result.projects[0]
        self.assertEqual(result.evidence["source"], "akbs_api")
        self.assertEqual(result.evidence["daily_package_keys"], ["20260610/member01/current-daily"])
        self.assertEqual(result.evidence["previous_weekly_package_keys"], ["20260607/member01/current-weekly"])
        self.assertEqual(result.evidence["missing_fields"], [])
        self.assertEqual(row["requirement_structure_counts"], {"demand": 2, "migration": 1, "bug": 1, "bsp": 0})
        self.assertEqual(row["completed_this_week_counts"], {"demand": 2, "migration": 0, "bug": 0, "bsp": 0})
        self.assertEqual(row["remaining_counts"], {"demand": 0, "migration": 0, "bug": 1, "bsp": 0})
        self.assertEqual(row["completed_items"], ["状态栏策略修改", "新增开关功能"])
        self.assertEqual(row["remaining_items"], ["修复亮度同步问题"])
        self.assertTrue(any("超过 3 天无进展" in item for item in row["risks"]))

    def test_weekly_history_includes_monday_boundary(self) -> None:
        load_intake_module()
        weekly_module = importlib.import_module("akbs_intake.reports.weekly_facts")
        monday = {
            "package_key": "20260608/member01/current-monday",
            "package_kind": "daily_trace",
            "report_date": "2026-06-08",
        }
        previous_sunday = {
            "package_key": "20260607/member01/previous-sunday",
            "package_kind": "daily_trace",
            "report_date": "2026-06-07",
        }

        def fake_fetch(_config: dict[str, str], package_kind: str, _month: str) -> list[dict]:
            return [previous_sunday, monday] if package_kind == "daily_trace" else []

        config = {
            "member_alias": "member01",
            "submission_api_base_url": "http://127.0.0.1:1/akbs/api",
            "weekly_history_api_enabled": "true",
        }
        with patch.object(weekly_module, "fetch_current_report_items", side_effect=fake_fetch):
            daily_items, weekly_items, provenance = weekly_module.load_history(
                config,
                dt.date(2026, 6, 8),
                dt.date(2026, 6, 14),
            )

        self.assertEqual([item["report_date"] for item in daily_items], ["2026-06-08"])
        self.assertEqual(weekly_items, [])
        self.assertEqual(provenance["daily_package_keys"], ["20260608/member01/current-monday"])

    def test_weekly_local_history_fallback_selects_replacement_leaf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            load_intake_module()
            weekly_module = importlib.import_module("akbs_intake.reports.weekly_facts")
            out_dir = root / "artifacts" / "android-knowledge-intake"

            def write_submitted(run_id: str, topic: str, replaces: str = "") -> None:
                package = out_dir / "submitted" / "20260610" / "member01" / run_id
                display = package / "materials" / "display" / "report_view.json"
                display.parent.mkdir(parents=True)
                display.write_text(
                    json.dumps(
                        {
                            "kind": "report_view",
                            "payload": {
                                "projects": [
                                    {
                                        "project": "TVE1086U",
                                        "customer": "青鸾云",
                                        "today_topic": topic,
                                        "work_items": [{"name": topic, "result": "已完成"}],
                                    }
                                ]
                            },
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                manifest = {
                    "package_kind": "daily_trace",
                    "member_alias": "member01",
                    "date": "2026-06-10",
                    "run_id": run_id,
                    "files": {"display": ["materials/display/report_view.json"]},
                }
                if replaces:
                    manifest["replacement_for_run_id"] = replaces
                (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            write_submitted("20260610-210000-daily", "错误旧事项")
            write_submitted("20260610-220000-daily", "补交后的正确事项", "20260610-210000-daily")

            rows = weekly_module.local_current_report_items(
                {"out_dir": str(out_dir), "member_alias": "member01"},
                "daily_trace",
                {"2026-06-10"},
            )

            self.assertEqual(len(rows), 1)
            self.assertIn("20260610-220000-daily", rows[0]["package_key"])
            self.assertEqual(rows[0]["report_view"]["projects"][0]["today_topic"], "补交后的正确事项")

    def test_session_summary_splits_multiple_projects_in_one_session(self) -> None:
        module = load_intake_module()
        session = module.SessionWork(
            session_id="77777777-3333-3333-4444-555555555555",
            project="TVE1086U",
            messages=[
                "TVE1086U 青鸾云，完成状态栏策略修改。",
                "TVA10A2R 灵犀屏，继续处理摄像头问题。",
            ],
            outcomes=[
                "TVE1086U 状态栏策略已完成并验证通过。",
                "TVA10A2R 摄像头问题仍在处理中。",
            ],
        )

        items = module.items_by_project([session], [])

        self.assertEqual(set(items), {"TVE1086U", "TVA10A2R"})
        self.assertEqual(items["TVE1086U"][0][1], "已完成")
        self.assertEqual(items["TVA10A2R"][0][1], "处理中")

    def test_daily_work_items_split_merge_and_use_fixed_status_values(self) -> None:
        module = load_intake_module()
        summary_module = importlib.import_module("akbs_intake.reports.session_summary")
        first = module.SessionWork(
            session_id="77777777-3333-3333-4444-555555555556",
            project="TVE1086U",
            latest_at="2026-06-03T10:00:00+08:00",
            messages=[
                "TVE1086U 青鸾云，1. 排查状态栏策略问题；2. 修改亮度同步逻辑。",
            ],
            outcomes=[
                "TVE1086U 状态栏策略问题已解决并验证通过。",
                "TVE1086U 亮度同步逻辑修改完成，待设备验证。",
            ],
            commands=["rg status_bar frameworks/base", "pytest tests/status_bar_test.py"],
        )
        second = module.SessionWork(
            session_id="77777777-3333-3333-4444-555555555557",
            project="TVE1086U",
            latest_at="2026-06-03T16:00:00+08:00",
            messages=["继续排查 TVE1086U 状态栏策略问题。"],
            outcomes=["TVE1086U 状态栏策略问题已解决并验证通过。"],
        )

        work_items = summary_module.daily_work_items_by_project([first, second], [])["TVE1086U"]

        self.assertEqual(len(work_items), 2)
        self.assertEqual({item["status"] for item in work_items}, {"已完成", "待验证"})
        self.assertTrue(any("检索并定位" in method for item in work_items for method in item["how"]))
        self.assertTrue(any("自动化检查" in method for item in work_items for method in item["how"]))
        self.assertFalse(any("rg status_bar" in method for item in work_items for method in item["how"]))

    def test_daily_work_item_statuses_do_not_leak_between_independent_items(self) -> None:
        module = load_intake_module()
        summary_module = importlib.import_module("akbs_intake.reports.session_summary")
        session = module.SessionWork(
            session_id="77777777-3333-3333-4444-555555555558",
            project="TVE1086U",
            latest_at="2026-06-03T16:00:00+08:00",
            messages=[
                "TVE1086U 青鸾云，1. 状态栏策略已完成；2. 亮度同步问题仍在处理中。",
            ],
        )

        work_items = summary_module.daily_work_items_by_project([session], [])["TVE1086U"]

        self.assertEqual([item["status"] for item in work_items], ["已完成", "处理中"])

    def test_report_local_check_rejects_missing_customer_and_command_text_customer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote, synthetic_data=False)
            codex_home = Path(env["CODEX_HOME"])
            source_root = create_framework_repo(root)

            write_codex_session(
                codex_home,
                "44444444-4444-3333-4444-555555555555",
                source_root,
                dt.date(2026, 6, 3),
                [
                    "TVE1086U 帮我生成日报并提交。",
                    "今天处理 TVE1086U 状态栏策略，进度100%。",
                ],
                thread_name="TVE1086U 日报",
            )

            daily = prepare_daily_package(env, "2026-06-03", "20260603-214000-daily")
            weekly = prepare_weekly_package(env, "2026-06-03", "20260603-224000-weekly")
            daily_check = json.loads((daily / "local-check.json").read_text(encoding="utf-8"))
            weekly_check = json.loads((weekly / "local-check.json").read_text(encoding="utf-8"))

            self.assertEqual(daily_check["status"], "FAIL")
            self.assertEqual(weekly_check["status"], "FAIL")
            self.assertIn("请按“项目名 客户名”补充", "\n".join(daily_check["errors"]))
            self.assertIn("请按“项目名 客户名”补充", "\n".join(weekly_check["errors"]))
            self.assertNotIn("帮我生成日报并提交", read_report_view(daily)["payload"]["projects"][0]["customer_name"])

    def test_weekly_project_ledger_rejects_source_directory_as_project_name(self) -> None:
        module = load_intake_module()

        rows = module.project_ledger_rows(
            {
                "b_mt8775_8792_tablet": [
                    ("完成 HDMI 副屏默认应用策略补充 mirror_display", "已完成"),
                ],
                "TVE1086U_MAIN_HANGYAN": [
                    ("完成锁屏鼠标位置刷新分析", "已完成"),
                ],
            }
        )

        projects = [row["project"] for row in rows]
        self.assertIn("TVE1086U", projects)
        self.assertIn("需成员补充项目名", projects)
        self.assertNotIn("b_mt8775_8792_tablet", projects)
        self.assertNotIn("TVE1086U_MAIN_HANGYAN", projects)

    def test_report_render_helpers_remain_available_from_intake_entrypoint(self) -> None:
        module = load_intake_module()

        self.assertTrue(callable(module.project_ledger_rows))
        self.assertTrue(callable(module.write_report))
        self.assertTrue(callable(module.write_report_view))

    def test_daily_records_discovered_patch_without_formal_patch_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote, synthetic_data=False)
            codex_home = Path(env["CODEX_HOME"])
            workdir = root / "member-work"
            workdir.mkdir()
            patch_file = workdir / "mtk15-frameworks-base@statusbar-policy.patch"
            patch_file.write_text(
                "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
                "--- a/frameworks/base/services/core/java/X.java\n"
                "+++ b/frameworks/base/services/core/java/X.java\n"
                "@@ -1 +1,2 @@\n"
                "+//gyf 20260602@ statusbar policy\n",
                encoding="utf-8",
            )
            patch_file.with_suffix(".readme.md").write_text("", encoding="utf-8")
            noon = dt.datetime(2026, 6, 2, 12, 0).timestamp()
            os.utime(patch_file, (noon, noon))
            os.utime(patch_file.with_suffix(".readme.md"), (noon, noon))
            write_codex_session(
                codex_home,
                "11111111-2222-3333-4444-555555555555",
                workdir,
                dt.date(2026, 6, 2),
                [
                    "TVE1086U 青鸾云，帮我生成日报并提交。",
                    "已完成 TVE1086U SystemUI 状态栏策略修改，后续需要补齐验证和 patch capture。",
                ],
            )

            result = run_json(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "daily",
                    "--date",
                    "2026-06-02",
                    "--run-id",
                    "20260602-210000-daily",
                    *SESSION_CONSENT_ARGS,
                    "--prepare",
                ],
                SUITE_ROOT,
                env,
            )

            package = Path(result["package"])
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            findings = json.loads((package / "materials" / "evidence" / "work_findings.json").read_text(encoding="utf-8"))

            self.assertEqual(result["local_check"]["status"], "PASS")
            self.assertEqual(manifest["package_kind"], "daily_trace")
            self.assertFalse((package / "patches").exists())
            self.assertTrue(
                any(
                    item["kind"] == "possible_framework_change"
                    and item["title"] == "mtk15-frameworks-base@statusbar-policy.patch"
                    and "需要 patch-capture 补齐 case/variant/风险/验证证据" in item["missing_evidence"]
                    for item in findings["payload"]["items"]
                )
            )

    def test_doctor_strict_passes_for_gray_profile_when_synthetic_is_explicitly_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote)
            clone_member_knowledge_worktree(root, remote)

            result = run_json(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "doctor",
                    "--strict",
                    "--check-remote",
                    "--allow-synthetic",
                ],
                SUITE_ROOT,
                env,
            )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["strict"]["errors"], [])

    def test_doctor_strict_rejects_synthetic_profile_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote)

            result = run(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "doctor",
                    "--strict",
                ],
                SUITE_ROOT,
                env,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("synthetic_data=true" in item for item in payload["strict"]["errors"]))

    def test_doctor_strict_requires_knowledge_worktree_clone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote, synthetic_data=False)

            result = run(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "doctor",
                    "--strict",
                ],
                SUITE_ROOT,
                env,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "PASS")
            self.assertTrue(any("knowledge_repo_worktree 不存在" in item for item in payload["strict"]["warnings"]))

    def test_daily_weekly_and_single_patch_upload_to_resolved_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge_remote = seed_knowledge_remote(root)
            env = write_member_config(root, knowledge_remote)

            with fake_upload_server() as (api_base_url, uploads):
                env["CODEX_REPORT_AKBS_ENDPOINT_SUBMISSION_API_BASE_URL"] = api_base_url

                daily = run_json(
                    [
                        sys.executable,
                        str(INTAKE_SCRIPT),
                        "--profile",
                        "member01",
                        "daily",
                        "--date",
                        "2026-06-01",
                        "--run-id",
                        "20260601-210000-daily",
                        "--upload",
                    ],
                    SUITE_ROOT,
                    env,
                )
                weekly = run_json(
                    [
                        sys.executable,
                        str(INTAKE_SCRIPT),
                        "--profile",
                        "member01",
                        "weekly",
                        "--date",
                        "2026-06-06",
                        "--run-id",
                        "20260606-220000-weekly",
                        "--upload",
                    ],
                    SUITE_ROOT,
                    env,
                )

                source_root = create_framework_repo(root)
                capture = run_json(
                    [
                        sys.executable,
                        str(CAPTURE_SCRIPT),
                        "--source-root",
                        str(source_root),
                        "--out-dir",
                        "capture-out",
                        "--run-id",
                        "20260601-120000-patch",
                        "--platform",
                        "mtk15",
                        "--feature",
                        "volume-dialog-position",
                        "--summary",
                        "通知音量弹窗位置适配",
                        "--project",
                        "TVE8402M",
                        "--status",
                        "validated",
                        "--verification",
                        "SystemUI 编译通过",
                        "--device",
                        "TVE8402M",
                        "--device-verification",
                        "通知音量弹窗位置符合项目验收要求",
                        "--search-query",
                        "通知音量 弹窗 位置 适配",
                        "--search-result",
                        "未发现可直接复用补丁",
                    ],
                    source_root,
                    env,
                )
                patch = run_json(
                    [
                        sys.executable,
                        str(INTAKE_SCRIPT),
                        "--profile",
                        "member01",
                        "patch",
                        "--date",
                        "2026-06-01",
                        "--run-id",
                        "20260601-230000-patch",
                        "--patch-package",
                        capture["package"],
                        "--summary",
                        "通知音量弹窗位置适配",
                        "--status",
                        "validated",
                        "--upload",
                    ],
                    SUITE_ROOT,
                    env,
                )
            daily_package = Path(daily["package"])
            weekly_package = Path(weekly["package"])
            patch_package = Path(patch["package"])
            daily_manifest = json.loads((daily_package / "manifest.json").read_text(encoding="utf-8"))
            weekly_manifest = json.loads((weekly_package / "manifest.json").read_text(encoding="utf-8"))
            patch_manifest = json.loads((patch_package / "manifest.json").read_text(encoding="utf-8"))
            patch_project = json.loads((patch_package / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))
            daily_findings = json.loads((daily_package / "materials" / "evidence" / "work_findings.json").read_text(encoding="utf-8"))
            weekly_findings = json.loads((weekly_package / "materials" / "evidence" / "work_findings.json").read_text(encoding="utf-8"))

            self.assertEqual(daily_manifest["package_kind"], "daily_trace")
            self.assertEqual(weekly_manifest["package_kind"], "weekly_trace")
            for findings in (daily_findings, weekly_findings):
                self.assertIn("codex_sessions", findings["payload"]["scanned_sources"])
                self.assertGreaterEqual(len(findings["payload"]["items"]), 1)
                self.assertTrue(
                    any(item["kind"] in {"work_record", "possible_framework_change"} for item in findings["payload"]["items"])
                )
            self.assertEqual(patch_manifest["package_kind"], "framework_change")
            self.assertEqual(patch_manifest["package_status"], "validated")
            self.assertEqual(patch_manifest["platform"], "mtk")
            self.assertEqual(patch_manifest["android_version"], "15")
            self.assertEqual(patch_manifest["project"], "TVE8402M")
            self.assertEqual(patch_project["payload"]["project"], "TVE8402M")
            self.assertTrue(patch_project["payload"]["company_rule_match"])
            self.assertIn("TVE8402M", (daily_package / "reports" / "daily.md").read_text(encoding="utf-8"))

            self.assertEqual(
                [item["path"] for item in uploads],
                [
                    "/akbs/api/member/me/uploads/daily",
                    "/akbs/api/member/me/uploads/weekly",
                    "/akbs/api/member/me/uploads/patch",
                ],
            )
            self.assertTrue(all(int(item["body_length"]) > 0 for item in uploads))
            for item in uploads:
                headers = {str(key).lower(): value for key, value in item["headers"].items()}
                self.assertEqual(headers.get("x-akbs-user"), "member01")
                for forbidden in ("x-akbs-token", "x-akbs-role", "x-akbs-client-ip", "x-forwarded-for", "x-real-ip", "cookie"):
                    self.assertNotIn(forbidden, headers)
            self.assertFalse((Path(env["CODEX_HOME"]) / "worktrees" / "knowledge-database-member01").exists())

    def test_daily_and_weekly_reports_include_human_template_and_ui_read_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge_remote = seed_knowledge_remote(root)
            env = write_member_config(root, knowledge_remote)

            daily = prepare_daily_package(env, "2026-06-30", "20260630-210000-daily")
            weekly = prepare_weekly_package(env, "2026-06-30", "20260630-220000-weekly")

            daily_report = read_package_report(daily, "daily")
            weekly_report = read_package_report(weekly, "weekly")
            for text in (
                "## 一、今日概况",
                "## 二、今日工作",
                "## 三、明日重点",
                "### **TVE8402M** 合成客户一",
                "- 今日主题：",
                "- 当前结果：",
                "做了什么：",
                "怎么做的：",
                "结果：",
                "状态：",
            ):
                self.assertIn(text, daily_report)
            for old_text in (
                "今日工作概览",
                "今日具体事项",
                "今日阻塞 / 风险",
                "今日产出",
                "事项来源",
                "处理方式/简要流程",
                "| 项目 | 客户 | 模块/功能 |",
            ):
                self.assertNotIn(old_text, daily_report)
            for text in (
                "## 一、本周概况",
                "## 二、项目详情",
                "## 三、下周计划",
                "### **TVE8402M** 合成客户一",
                "项目角色",
                "需求时间",
                "需求来源",
                "本周完成",
                "当前剩余",
                "#### 1. 本周完成",
                "#### 2. 当前剩余",
                "#### 3. 重点说明",
                "#### 4. 风险 / 依赖",
            ):
                self.assertIn(text, weekly_report)
            for old_text in ("#### 1. 基本信息", "来源类型", "上周一剩余", "当周完成情况", "移植适配"):
                self.assertNotIn(old_text, weekly_report)
            daily_view = read_report_view(daily)
            weekly_view = read_report_view(weekly)
            unbolded_project = re.compile(
                r"(?<!\*)TV[DEAI]\d{2}[A-Z0-9]{2}[MRU]\d?(?![A-Z0-9*])",
                re.IGNORECASE,
            )
            self.assertIsNone(unbolded_project.search(daily_report), daily_report)
            self.assertIsNone(unbolded_project.search(weekly_report), weekly_report)
            self.assertEqual(daily_view["kind"], "report_view")
            self.assertEqual(daily_view["payload"]["schema"], "akbs-report-view-human-v1")
            self.assertEqual(daily_view["payload"]["report_type"], "daily")
            self.assertEqual(daily_view["payload"]["report_date"], "2026-06-30")
            self.assertEqual(daily_view["payload"]["material_name"], "TVE8402M（合成客户一）")
            self.assertNotIn("**", daily_view["payload"]["material_name"])
            self.assertIn("TVE8402M：", daily_view["payload"]["material_summary"])
            self.assertGreaterEqual(len(daily_view["payload"]["projects"]), 1)
            for old_field in ("ui_card", "one_line_summary", "display_title", "daily_overview", "work_items", "items", "outputs", "next_steps"):
                self.assertNotIn(old_field, daily_view["payload"])
            daily_project = daily_view["payload"]["projects"][0]
            self.assertEqual(daily_project["project"], "TVE8402M")
            self.assertEqual(daily_project["customer"], "合成客户一")
            for field in ("today_topic", "current_result", "work_items", "tomorrow_focus"):
                self.assertIn(field, daily_project)
            daily_item = daily_project["work_items"][0]
            for field in ("name", "did", "how", "result", "status"):
                self.assertIn(field, daily_item)
            self.assertIn(daily_item["status"], {"已完成", "处理中", "待验证", "阻塞"})
            self.assertEqual(weekly_view["kind"], "report_view")
            self.assertEqual(weekly_view["payload"]["schema"], "akbs-report-view-human-v1")
            self.assertEqual(weekly_view["payload"]["report_type"], "weekly")
            self.assertEqual(weekly_view["payload"]["display_date"], "2026-07-03")
            self.assertEqual(weekly_view["payload"]["material_name"], "TVE8402M（合成客户一）")
            self.assertNotIn("**", weekly_view["payload"]["material_name"])
            self.assertIn("TVE8402M：本周完成", weekly_view["payload"]["material_summary"])
            for old_field in (
                "ui_card",
                "one_line_summary",
                "display_title",
                "project_overview",
                "source_lists",
                "source_category_stats",
                "project_ledgers",
                "weekly_detail_sections",
                "weekly_progress_summary",
                "patch_outputs",
                "delivery_verifications",
            ):
                self.assertNotIn(old_field, weekly_view["payload"])
            self.assertGreaterEqual(len(weekly_view["payload"]["projects"]), 1)
            ledger = weekly_view["payload"]["projects"][0]
            for field in (
                "project",
                "customer",
                "project_role",
                "week_summary",
                "requirement_date",
                "requirement_source",
                "requirement_structure",
                "completed_this_week",
                "remaining",
                "completed_items",
                "remaining_items",
                "key_points",
                "risks",
                "dependencies",
                "next_week_plan",
            ):
                self.assertIn(field, ledger)
            self.assertIn(ledger["project_role"], {"主责", "协作"})
            self.assertIn(ledger["requirement_source"], {"CR", "TL", "PM", "TE", "BSP"})

            daily_manifest = json.loads((daily / "manifest.json").read_text(encoding="utf-8"))
            weekly_manifest = json.loads((weekly / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(daily_manifest["files"]["display"], ["materials/display/report_view.json"])
            self.assertEqual(weekly_manifest["files"]["display"], ["materials/display/report_view.json"])
            self.assertTrue((daily / "materials" / "evidence" / "work_findings.json").is_file())
            self.assertTrue((weekly / "materials" / "evidence" / "work_findings.json").is_file())

    def test_daily_future_date_blocks_late_submission_allows_and_duplicate_requires_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge_remote = seed_knowledge_remote(root)
            env = write_member_config(root, knowledge_remote)

            future = run(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "daily",
                    "--date",
                    "2099-01-01",
                    "--run-id",
                    "20990101-210000-daily",
                    "--prepare",
                ],
                SUITE_ROOT,
                env,
                check=False,
            )

            self.assertNotEqual(future.returncode, 0)
            self.assertIn("不能提交未来日期的日报", future.stderr)

            first = prepare_daily_package(env, "2026-06-29", "20260629-210000-daily")
            first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(first_manifest["date"], "2026-06-29")

            duplicate = run(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "daily",
                    "--date",
                    "2026-06-29",
                    "--run-id",
                    "20260629-210001-daily",
                    "--prepare",
                ],
                SUITE_ROOT,
                env,
                check=False,
            )

            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("同一成员同一日报日期已存在日报包", duplicate.stderr)
            self.assertIn("--replace-daily-run-id 20260629-210000-daily", duplicate.stderr)
            self.assertIn("如不替换，请取消本次提交", duplicate.stderr)

            replacement = prepare_replacement_package(
                env,
                "daily",
                "2026-06-29",
                "20260629-210002-daily",
                "20260629-210000-daily",
            )
            manifest = json.loads((replacement / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["replacement_for_run_id"], "20260629-210000-daily")
            self.assertEqual(manifest["supersedes"]["report_type"], "daily")
            self.assertEqual(manifest["supersedes"]["identity"], "2026-06-29")
            self.assertEqual(manifest["supersedes"]["package_key"], "20260629/member01/20260629-210000-daily")

    def test_weekly_future_period_blocks_and_late_period_allows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge_remote = seed_knowledge_remote(root)
            env = write_member_config(root, knowledge_remote)

            future = run(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "weekly",
                    "--date",
                    "2099-01-05",
                    "--run-id",
                    "20990105-220000-weekly",
                    "--prepare",
                ],
                SUITE_ROOT,
                env,
                check=False,
            )

            self.assertNotEqual(future.returncode, 0)
            self.assertIn("不能提交未来周期的周报", future.stderr)

            late = prepare_weekly_package(env, "2026-06-22", "20260622-220000-weekly")
            manifest = json.loads((late / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["week_range"], "20260622-20260628")

    def test_weekly_prepare_blocks_duplicate_week_range_without_affecting_daily_or_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge_remote = seed_knowledge_remote(root)
            env = write_member_config(root, knowledge_remote)

            first = prepare_weekly_package(env, "2026-06-18", "20260618-090102")
            first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(first_manifest["week_range"], "20260615-20260621")

            duplicate = run(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "weekly",
                    "--date",
                    "2026-06-18",
                    "--run-id",
                    "20260618-090103",
                    "--prepare",
                ],
                SUITE_ROOT,
                env,
                check=False,
            )

            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("同一成员同一周报周期已存在周报包", duplicate.stderr)
            self.assertIn("--replace-weekly-run-id 20260618-090102", duplicate.stderr)
            self.assertIn("如不替换，请取消本次提交", duplicate.stderr)

            daily = prepare_daily_package(env, "2026-06-18", "20260618-210000-daily")
            self.assertEqual(
                json.loads((daily / "manifest.json").read_text(encoding="utf-8"))["package_kind"],
                "daily_trace",
            )

            patch = run_json(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "patch",
                    "--date",
                    "2026-06-18",
                    "--run-id",
                    "20260618-230000-patch",
                    "--project",
                    "TVE8402M",
                    "--summary",
                    "周报重复防护不影响补丁包",
                    "--status",
                    "candidate",
                    "--prepare",
                ],
                SUITE_ROOT,
                env,
            )
            self.assertEqual(
                json.loads((Path(patch["package"]) / "manifest.json").read_text(encoding="utf-8"))["package_kind"],
                "framework_change",
            )

    def test_weekly_upload_records_submitted_guard_and_explicit_replacement_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge_remote = seed_knowledge_remote(root)
            env = write_member_config(root, knowledge_remote)

            with fake_upload_server() as (api_base_url, uploads):
                env["CODEX_REPORT_AKBS_ENDPOINT_SUBMISSION_API_BASE_URL"] = api_base_url
                first = run_json(
                    [
                        sys.executable,
                        str(INTAKE_SCRIPT),
                        "--profile",
                        "member01",
                        "weekly",
                        "--date",
                        "2026-06-18",
                        "--run-id",
                        "20260618-090102",
                        "--upload",
                    ],
                    SUITE_ROOT,
                    env,
                )
                self.assertEqual([item["path"] for item in uploads], ["/akbs/api/member/me/uploads/weekly"])
            first_package = Path(first["package"])
            submitted_manifest = (
                Path(env["CODEX_HOME"]).parent
                / "artifacts"
                / "android-knowledge-intake"
                / "submitted"
                / "20260618"
                / "member01"
                / "20260618-090102"
                / "manifest.json"
            )
            self.assertTrue(submitted_manifest.is_file())
            shutil.rmtree(first_package)

            duplicate = run(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "weekly",
                    "--date",
                    "2026-06-18",
                    "--run-id",
                    "20260618-090103",
                    "--prepare",
                ],
                SUITE_ROOT,
                env,
                check=False,
            )

            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("submitted:20260618/member01/20260618-090102", duplicate.stderr)

            replacement = prepare_replacement_package(
                env,
                "weekly",
                "2026-06-18",
                "20260618-090103",
                "20260618-090102",
            )
            manifest = json.loads((replacement / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["replacement_for_run_id"], "20260618-090102")
            self.assertEqual(manifest["supersedes"]["week_range"], "20260615-20260621")
            self.assertEqual(manifest["supersedes"]["identity"], "20260615-20260621")
            self.assertEqual(manifest["supersedes"]["package_key"], "20260618/member01/20260618-090102")

    def test_non_company_project_is_not_preserved_as_project_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote)
            patch_file = root / "mtk15-frameworks-base@statusbar-policy.patch"
            readme_file = root / "mtk15-frameworks-base@statusbar-policy.readme.md"
            patch_file.write_text(
                "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
                "--- a/frameworks/base/services/core/java/X.java\n"
                "+++ b/frameworks/base/services/core/java/X.java\n"
                "@@ -1 +1,2 @@\n"
                "+//gyf 20260601@ statusbar policy\n",
                encoding="utf-8",
            )
            readme_file.write_text(
                "# statusbar policy\n\n"
                "## 功能描述\n\n状态栏策略调整。\n\n"
                "## 修改点\n\n- 修改 frameworks/base。\n\n"
                "## 日志控制\n\n无。\n\n"
                "## SystemProperties\n\n无。\n\n"
                "## 字符串国际化\n\n无。\n\n"
                "## 可回滚性\n\n可回滚。\n",
                encoding="utf-8",
            )

            result = run_json(
                [
                    sys.executable,
                    str(INTAKE_SCRIPT),
                    "--profile",
                    "member01",
                    "patch",
                    "--date",
                    "2026-06-01",
                    "--run-id",
                    "20260601-231000-patch",
                    "--patch",
                    str(patch_file),
                    "--project",
                    "Generic Framework",
                    "--summary",
                    "状态栏策略调整",
                    "--status",
                    "candidate",
                    "--prepare",
                ],
                SUITE_ROOT,
                env,
            )
            package = Path(result["package"])
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            project = json.loads((package / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "unknown")
            self.assertFalse(project["payload"]["recognized"])
            self.assertIn("未作为项目名写入上传包", " ".join(project["payload"]["limits"]))


if __name__ == "__main__":
    unittest.main()
