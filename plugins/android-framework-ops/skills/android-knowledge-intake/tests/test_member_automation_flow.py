from __future__ import annotations

import datetime as dt
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SUITE_ROOT = Path(__file__).resolve().parents[5]
INTAKE_SCRIPT = SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "scripts" / "android_knowledge_intake.py"
CAPTURE_SCRIPT = SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-framework-patch-capture" / "scripts" / "capture_framework_patch.py"
MIGRATION_PROMPT = SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "references" / "member-migration-prompt.md"
MEMBER_BOUNDARY_DOCS = (
    SUITE_ROOT / "README.md",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "README.md",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "SKILL.md",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "agents" / "openai.yaml",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "config.example.toml",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "references" / "incoming-package-protocol.md",
    MIGRATION_PROMPT,
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-framework-patch-capture" / "SKILL.md",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-framework-patch-capture" / "references" / "package-contract.md",
    SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-search" / "SKILL.md",
    SUITE_ROOT / "docs" / "skills" / "android-framework-ops" / "android-knowledge-intake" / "README.md",
    SUITE_ROOT / "docs" / "skills" / "android-framework-ops" / "android-framework-patch-capture" / "README.md",
    SUITE_ROOT / "docs" / "skills" / "android-framework-ops" / "android-knowledge-search" / "README.md",
)


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


def write_member_config(root: Path, knowledge_remote: Path, submit_command: str | None = None, synthetic_data: bool = True) -> dict[str, str]:
    codex_home = root / "codex-home"
    config_dir = codex_home / "report"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        textwrap.dedent(
            f"""
            default_profile = "member01"
            incoming_schema_version = "1"

            [submission]
            method = "local"
            command = "{submit_command or "python3 -c 'import sys; sys.exit(0)'"}"

            [knowledge]
            repo_url = "{knowledge_remote.as_posix()}"

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


def write_local_submitter(root: Path, database_root: Path) -> str:
    script = root / "local-submit.py"
    script.write_text(
        textwrap.dedent(
            """
            from __future__ import annotations

            import argparse
            import json
            import shutil
            import sys
            import tarfile
            import tempfile
            from pathlib import Path

            parser = argparse.ArgumentParser()
            parser.add_argument("--root", required=True)
            parser.add_argument("--member", required=True)
            parser.add_argument("--stdin-tar-gz", action="store_true")
            args = parser.parse_args()
            if not args.stdin_tar_gz:
                raise SystemExit("--stdin-tar-gz is required")
            root = Path(args.root)
            with tempfile.TemporaryDirectory() as tmp:
                package = Path(tmp) / "package"
                package.mkdir()
                archive_path = Path(tmp) / "package.tar.gz"
                archive_path.write_bytes(sys.stdin.buffer.read())
                with tarfile.open(archive_path, "r:gz") as archive:
                    for member in archive.getmembers():
                        target = (package / member.name).resolve()
                        if package.resolve() not in target.parents and target != package.resolve():
                            raise SystemExit("path traversal")
                    archive.extractall(package)
                manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
                if manifest["member_alias"] != args.member:
                    raise SystemExit("member mismatch")
                date_key = manifest["date"].replace("-", "")
                target = root / "incoming" / date_key / manifest["member_alias"] / manifest["run_id"]
                if target.exists():
                    raise SystemExit("target exists")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(package, target)
                print(json.dumps({"submitted": True, "path": str(target)}, ensure_ascii=False))
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return f"{sys.executable} {script} --root {database_root}"


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
            "/home/test35/work/akbs/database-worktree/scripts/akbs-submit",
            "git clone test35:/home/test35/work/akbs/database.git",
            "git clone /home/test35/work/akbs/database.git",
        ]
        for term in forbidden:
            self.assertNotIn(term, combined)

        member_only_docs = (
            SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "SKILL.md",
            SUITE_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "config.example.toml",
            MIGRATION_PROMPT,
            SUITE_ROOT / "docs" / "skills" / "android-framework-ops" / "android-knowledge-intake" / "README.md",
        )
        member_text = "\n".join(path.read_text(encoding="utf-8") for path in member_only_docs)
        self.assertNotIn("database_repo_worktree", member_text)
        self.assertNotIn("knowledge-database-", member_text)
        self.assertIn("server submission channel", member_text)
        self.assertIn("akbs-curation-maintainer", combined)
        self.assertIn("周报包", member_text)
        self.assertIn("不进入知识库仓库", member_text)

    def test_member_migration_prompt_covers_update_and_dual_repositories(self) -> None:
        text = MIGRATION_PROMPT.read_text(encoding="utf-8")

        self.assertIn("首次启用提示词", text)
        self.assertIn("插件更新（plugin update）", text)
        self.assertIn("新配置（new configuration）", text)
        self.assertIn("服务器上传入口（server upload endpoint）", text)
        self.assertIn("/home/test35/work/akbs/database-intake-worktree/scripts/akbs-submit", text)
        self.assertNotIn("/home/test35/work/akbs/database-worktree/scripts/akbs-submit", text)
        self.assertIn("test35:/home/test35/work/akbs/knowledge.git", text)
        self.assertIn('git clone test35:/home/test35/work/akbs/knowledge.git "$CODEX_HOME/worktrees/knowledge"', text)
        self.assertIn('git -C "$CODEX_HOME/worktrees/knowledge" pull --ff-only', text)
        self.assertIn("doctor --strict --check-remote", text)
        self.assertNotIn("database_repo_worktree", text)
        self.assertNotIn("remote.git", text)
        self.assertNotIn("config-migrate", text)

    def test_git_submission_mode_is_not_supported(self) -> None:
        module = load_intake_module()

        with self.assertRaises(SystemExit) as caught:
            module.submission_method({"submission_method": "git"})

        self.assertIn("不支持", str(caught.exception))

    def test_plugin_freshness_detects_checkout_behind_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = seed_stale_plugin_checkout(root)
            module = load_intake_module()
            module.PLUGIN_ROOT = plugin_root

            result = module.plugin_freshness_check(fetch=True)

            self.assertEqual(result["status"], "STALE")
            self.assertTrue(result["blocking"])
            self.assertIn("插件有更新", result["message"])
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

    def test_packaged_plugin_freshness_detects_newer_marketplace_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = seed_packaged_plugin_install(root, version="1.0.24")
            module = load_intake_module()
            module.PLUGIN_ROOT = plugin_root
            module.fetch_remote_plugin_manifest = lambda metadata: {"version": "1.0.26"}

            result = module.plugin_freshness_check(fetch=True)

            self.assertEqual(result["status"], "STALE")
            self.assertTrue(result["blocking"])
            self.assertEqual(result["local_version"], "1.0.24")
            self.assertEqual(result["remote_version"], "1.0.26")
            self.assertIn("插件有更新", result["message"])

    def test_source_metadata_records_packaged_plugin_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_root = seed_packaged_plugin_install(root, version="1.0.24")
            module = load_intake_module()
            module.PLUGIN_ROOT = plugin_root

            source = module.source_metadata({"member_alias": "member01"}, "android-knowledge-intake")

            self.assertEqual(source["plugin_name"], "android-framework-ops")
            self.assertEqual(source["plugin_version"], "1.0.24")
            self.assertEqual(source["skill_version"], "1.0.24")
            self.assertEqual(source["plugin_installation"], "packaged")

    def test_member_generation_modes_stop_when_plugin_checkout_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
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
                for mode in ("daily", "weekly", "patch"):
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

                        with contextlib.redirect_stdout(stdout):
                            code = module.main()

                        self.assertEqual(code, 1)
                        payload = json.loads(stdout.getvalue())
                        self.assertEqual(payload["status"], "FAIL")
                        self.assertEqual(payload["plugin_freshness"]["status"], "STALE")
                        self.assertIn("插件有更新", payload["message"])
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

            def unknown_freshness(fetch: bool = True, require: bool = False) -> dict:
                calls.append((fetch, require))
                return {
                    "status": "UNKNOWN",
                    "blocking": require,
                    "message": "无法确认插件是否为最新版本。",
                }

            module.plugin_freshness_check = unknown_freshness
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

            result = run_json(
                [sys.executable, str(INTAKE_SCRIPT), "--profile", "member01", "doctor"],
                SUITE_ROOT,
                env,
            )

            self.assertEqual(result["submission_method"], "local")
            self.assertIn("submission_command", result)
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
            self.assertIn("### TVA10A2R", report)
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
            self.assertIn("### TVE1086U", report)
            self.assertIn("整体项目交接", report)
            self.assertNotIn("### TVE1086U整体项目交接", report)
            self.assertNotIn("### android16", report)

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
                "已完成 SystemUI 状态栏策略修改，后续需要补齐验证和 patch capture。",
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

            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "FAIL")
            self.assertTrue(any("knowledge_repo_worktree 不存在" in item for item in payload["strict"]["errors"]))

    def test_daily_weekly_and_patch_upload_to_simulated_incoming_remote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            knowledge_remote = seed_knowledge_remote(root)
            database_root = root / "server-database"
            submit_command = write_local_submitter(root, database_root)
            env = write_member_config(root, knowledge_remote, submit_command)

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

            expected = [
                database_root / "incoming" / "20260601" / "member01" / "20260601-210000-daily" / "manifest.json",
                database_root / "incoming" / "20260606" / "member01" / "20260606-220000-weekly" / "manifest.json",
                database_root / "incoming" / "20260601" / "member01" / "20260601-230000-patch" / "manifest.json",
            ]
            for path in expected:
                self.assertTrue(path.is_file(), path)
            self.assertFalse((Path(env["CODEX_HOME"]) / "worktrees" / "knowledge-database-member01").exists())

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
