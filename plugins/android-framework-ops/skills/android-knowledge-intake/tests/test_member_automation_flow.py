from __future__ import annotations

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


def run_json(cmd: list[str], cwd: Path, env: dict[str, str]) -> dict:
    result = run(cmd, cwd, env)
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


def write_member_config(root: Path, remote: Path) -> dict[str, str]:
    codex_home = root / "codex-home"
    config_dir = codex_home / "report"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        textwrap.dedent(
            f"""
            default_profile = "member01"
            incoming_schema_version = "1"

            [server]
            repo_url = "{remote.as_posix()}"

            [paths]
            out_dir = "{(root / "artifacts" / "android-knowledge-intake").as_posix()}"

            [profiles.member01]
            member_alias = "member01"
            member_name = "成员甲"
            role = "member"
            allowed_modes = ["daily", "weekly", "patch"]
            repo_worktree = "{(root / "worktrees" / "knowledge-member01").as_posix()}"
            git_user_name = "成员甲"
            git_user_email = "member01@example.invalid"
            synthetic_data = true
            synthetic_item_count = "2"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    return env


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
    def test_doctor_strict_passes_for_gray_profile_when_synthetic_is_explicitly_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote)

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

    def test_daily_weekly_and_patch_upload_to_simulated_incoming_remote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = seed_knowledge_remote(root)
            env = write_member_config(root, remote)

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
            patch_project = json.loads((patch_package / "knowledge" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))
            daily_findings = json.loads((daily_package / "knowledge" / "evidence" / "work_findings.json").read_text(encoding="utf-8"))
            weekly_findings = json.loads((weekly_package / "knowledge" / "evidence" / "work_findings.json").read_text(encoding="utf-8"))

            self.assertEqual(daily_manifest["package_kind"], "daily_trace")
            self.assertEqual(weekly_manifest["package_kind"], "weekly_trace")
            for findings in (daily_findings, weekly_findings):
                self.assertIn("codex_sessions", findings["payload"]["scanned_sources"])
                self.assertGreaterEqual(len(findings["payload"]["items"]), 1)
                self.assertTrue(
                    any(item["kind"] in {"work_record", "possible_framework_change"} for item in findings["payload"]["items"])
                )
            self.assertEqual(patch_manifest["package_kind"], "framework_change")
            self.assertEqual(patch_manifest["maturity"], "validated")
            self.assertEqual(patch_manifest["platform"], "mtk")
            self.assertEqual(patch_manifest["android_version"], "15")
            self.assertEqual(patch_manifest["project"], "TVE8402M")
            self.assertEqual(patch_project["payload"]["project"], "TVE8402M")
            self.assertTrue(patch_project["payload"]["company_rule_match"])
            self.assertIn("TVE8402M", (daily_package / "reports" / "daily.md").read_text(encoding="utf-8"))

            clone = root / "remote-checkout"
            run(["git", "clone", str(remote), str(clone)], root)
            expected = [
                clone / "incoming" / "20260601" / "member01" / "20260601-210000-daily" / "manifest.json",
                clone / "incoming" / "20260606" / "member01" / "20260606-220000-weekly" / "manifest.json",
                clone / "incoming" / "20260601" / "member01" / "20260601-230000-patch" / "manifest.json",
            ]
            for path in expected:
                self.assertTrue(path.is_file(), path)

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
            project = json.loads((package / "knowledge" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "unknown")
            self.assertFalse(project["payload"]["recognized"])
            self.assertIn("未作为项目名入库", " ".join(project["payload"]["limits"]))


if __name__ == "__main__":
    unittest.main()
