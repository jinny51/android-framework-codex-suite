from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
SKILL_DIR = REPO_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-framework-patch-capture"
SCRIPT = SKILL_DIR / "scripts" / "capture_framework_patch.py"
LIB_ROOT = REPO_ROOT / "plugins" / "android-framework-ops" / "lib"
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

from android_framework_ops.remote_patch_snapshot import create_remote_patch_snapshot


def load_patch_capture_module():
    spec = __import__("importlib.util").util.spec_from_file_location("capture_framework_patch_under_test", SCRIPT)
    assert spec and spec.loader
    module = __import__("importlib.util").util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    command = list(cmd)
    env = os.environ.copy()
    if len(command) > 1 and Path(command[1]) == SCRIPT and "--source-root" in command:
        if "--workflow-contract" not in command:
            command.extend(["--workflow-contract", "manual_import"])
        else:
            contract = command[command.index("--workflow-contract") + 1]
            if contract == "current_codex_skill":
                source_roots: list[Path] = []
                while "--source-root" in command:
                    index = command.index("--source-root")
                    source_roots.append(Path(command[index + 1]).resolve())
                    del command[index : index + 2]
                if len(source_roots) != 1:
                    raise AssertionError("current snapshot test helper expects one source root")
                remote_root = source_roots[0]
                workspace_id = hashlib.sha256(str(remote_root).encode()).hexdigest()[:16]
                run_id = command[command.index("--run-id") + 1]
                command_id = f"snapshot-{run_id}"[:128]
                snapshot = create_remote_patch_snapshot(
                    remote_root=remote_root,
                    workspace_id=workspace_id,
                    command_id=command_id,
                    repository_paths=["."],
                    generated_at_ns=time.time_ns(),
                )
                snapshot_path = Path(cwd) / f".{command_id}.json"
                snapshot_path.write_text(
                    json.dumps(snapshot, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                command.extend(
                    [
                        "--remote-snapshot",
                        str(snapshot_path),
                        "--snapshot-workspace-id",
                        workspace_id,
                        "--snapshot-command-id",
                        command_id,
                        "--snapshot-sha256",
                        snapshot["snapshot_sha256"],
                        "--remote-source-root",
                        str(remote_root),
                    ]
                )
                codex_home = Path(cwd) / ".codex-test-home"
                env["CODEX_HOME"] = str(codex_home)
                codex_home.mkdir(parents=True, exist_ok=True)
                (codex_home / "android-knowledge-intake.toml").write_text(
                    "default_profile = \"member01\"\n\n"
                    "[profiles.member01]\n"
                    "member_alias = \"member01\"\n"
                    "member_name = \"Member 01\"\n"
                    "timezone = \"Asia/Shanghai\"\n",
                    encoding="utf-8",
                )
                if "--profile" not in command:
                    command.extend(["--profile", "member01"])
                if "--out-dir" in command:
                    output_index = command.index("--out-dir") + 1
                    command[output_index] = str(codex_home / "artifacts" / command[output_index])
    result = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result


def create_repo(root: Path) -> None:
    run(["git", "init"], root)
    run(["git", "config", "user.email", "codex@example.invalid"], root)
    run(["git", "config", "user.name", "Codex Test"], root)
    source = root / "frameworks" / "base" / "services" / "core" / "java" / "com" / "android" / "server" / "wm"
    source.mkdir(parents=True)
    (source / "DisplayPolicy.java").write_text("class DisplayPolicy {}\n", encoding="utf-8")
    run(["git", "add", "."], root)
    run(["git", "commit", "-m", "initial"], root)
    (source / "DisplayPolicy.java").write_text(
        "class DisplayPolicy {\n"
        "  //member01 20260526@{\n"
        "  static final String KEY = \"persist.sys.nav_policy\";\n"
        "  //member01 20260526@}\n"
        "}\n",
        encoding="utf-8",
    )


def create_plain_repo(root: Path) -> None:
    run(["git", "init"], root)
    run(["git", "config", "user.email", "codex@example.invalid"], root)
    run(["git", "config", "user.name", "Codex Test"], root)
    source = root / "frameworks" / "base" / "services" / "core" / "java" / "com" / "android" / "server" / "wm"
    source.mkdir(parents=True)
    (source / "DisplayPolicy.java").write_text("class DisplayPolicy {}\n", encoding="utf-8")
    run(["git", "add", "."], root)
    run(["git", "commit", "-m", "initial"], root)
    (source / "DisplayPolicy.java").write_text(
        "class DisplayPolicy {\n"
        "  //legacy_author 20260604@ plain policy update\n"
        "}\n",
        encoding="utf-8",
    )


def create_audio_camera_repo(root: Path) -> None:
    run(["git", "init"], root)
    run(["git", "config", "user.email", "codex@example.invalid"], root)
    run(["git", "config", "user.name", "Codex Test"], root)
    audio = root / "frameworks" / "base" / "services" / "core" / "java" / "com" / "android" / "server" / "audio"
    camera = root / "frameworks" / "av" / "services" / "camera" / "libcameraservice"
    audio.mkdir(parents=True)
    camera.mkdir(parents=True)
    (audio / "AudioService.java").write_text("class AudioService {}\n", encoding="utf-8")
    (camera / "CameraService.cpp").write_text("class CameraService {};\n", encoding="utf-8")
    run(["git", "add", "."], root)
    run(["git", "commit", "-m", "initial"], root)
    (audio / "AudioService.java").write_text(
        "class AudioService {\n"
        "  //legacy_author 20260530@ adjust microphone route fallback\n"
        "  static final String MIC_POLICY = \"persist.sys.mic_policy\";\n"
        "}\n",
        encoding="utf-8",
    )
    (camera / "CameraService.cpp").write_text(
        "class CameraService {\n"
        "  //legacy_author 20260530@ align camera permission fallback\n"
        "};\n",
        encoding="utf-8",
    )


def create_launcher_repo(root: Path) -> None:
    run(["git", "init"], root)
    run(["git", "config", "user.email", "codex@example.invalid"], root)
    run(["git", "config", "user.name", "Codex Test"], root)
    source = root / "packages" / "apps" / "Launcher3" / "src" / "com" / "android" / "launcher3"
    source.mkdir(parents=True)
    (source / "Workspace.java").write_text("class Workspace {}\n", encoding="utf-8")
    run(["git", "add", "."], root)
    run(["git", "commit", "-m", "initial"], root)
    (source / "Workspace.java").write_text(
        "class Workspace {\n"
        "  //legacy_author 20260728@ keep workspace labels centered\n"
        "  static final boolean CENTER_LABELS = true;\n"
        "}\n",
        encoding="utf-8",
    )


def create_frameworks_base_repo(root: Path) -> None:
    run(["git", "init"], root)
    run(["git", "config", "user.email", "codex@example.invalid"], root)
    run(["git", "config", "user.name", "Codex Test"], root)
    source = root / "services" / "core" / "java" / "com" / "android" / "server" / "wm"
    source.mkdir(parents=True)
    (source / "DisplayPolicy.java").write_text("class DisplayPolicy {}\n", encoding="utf-8")
    run(["git", "add", "."], root)
    run(["git", "commit", "-m", "initial"], root)
    (source / "DisplayPolicy.java").write_text(
        "class DisplayPolicy {\n"
        "  //legacy_author 20260608@ align cross repo feature policy\n"
        "  static final String KEY = \"persist.sys.cross_repo_policy\";\n"
        "}\n",
        encoding="utf-8",
    )


def create_settings_repo(root: Path) -> None:
    run(["git", "init"], root)
    run(["git", "config", "user.email", "codex@example.invalid"], root)
    run(["git", "config", "user.name", "Codex Test"], root)
    source = root / "src" / "com" / "android" / "settings"
    source.mkdir(parents=True)
    (source / "DisplaySettings.java").write_text("class DisplaySettings {}\n", encoding="utf-8")
    run(["git", "add", "."], root)
    run(["git", "commit", "-m", "initial"], root)
    (source / "DisplaySettings.java").write_text(
        "class DisplaySettings {\n"
        "  //legacy_author 20260608@ expose cross repo feature switch\n"
        "}\n",
        encoding="utf-8",
    )


def create_mode_only_repo(root: Path) -> Path:
    run(["git", "init"], root)
    run(["git", "config", "user.email", "codex@example.invalid"], root)
    run(["git", "config", "user.name", "Codex Test"], root)
    source = root / "frameworks" / "base" / "services" / "core" / "java" / "com" / "android" / "server" / "wm"
    source.mkdir(parents=True)
    file_path = source / "DisplayPolicy.java"
    file_path.write_text(
        "class DisplayPolicy {\n"
        "  //legacy_author 20260615@ existing feature marker\n"
        "}\n",
        encoding="utf-8",
    )
    file_path.chmod(0o755)
    run(["git", "add", "."], root)
    run(["git", "update-index", "--chmod=+x", str(file_path.relative_to(root))], root)
    run(["git", "commit", "-m", "initial executable mode"], root)
    run(["git", "update-index", "--chmod=-x", str(file_path.relative_to(root))], root)
    return file_path


def create_repo_with_mode_noise(root: Path) -> tuple[Path, Path]:
    run(["git", "init"], root)
    run(["git", "config", "user.email", "codex@example.invalid"], root)
    run(["git", "config", "user.name", "Codex Test"], root)
    source = root / "frameworks" / "base" / "services" / "core" / "java" / "com" / "android" / "server" / "wm"
    tool_dir = root / "tools"
    source.mkdir(parents=True)
    tool_dir.mkdir(parents=True)
    file_path = source / "DisplayPolicy.java"
    mode_noise_path = tool_dir / "mode-noise.sh"
    file_path.write_text("class DisplayPolicy {}\n", encoding="utf-8")
    mode_noise_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    run(["git", "add", "."], root)
    run(["git", "update-index", "--chmod=+x", str(mode_noise_path.relative_to(root))], root)
    run(["git", "commit", "-m", "initial mixed mode repo"], root)
    file_path.write_text(
        "class DisplayPolicy {\n"
        "  //legacy_author 20260615@ keep content diff while dropping mode noise\n"
        "  static final String KEY = \"persist.sys.mode_noise\";\n"
        "}\n",
        encoding="utf-8",
    )
    run(["git", "update-index", "--chmod=-x", str(mode_noise_path.relative_to(root))], root)
    return file_path, mode_noise_path


class CaptureFrameworkPatchTests(unittest.TestCase):
    def test_facts_from_diff_extract_added_xml_string_resource_names(self) -> None:
        module = load_patch_capture_module()

        facts = module.facts_from_diff(
            "diff --git a/res/values/strings.xml b/res/values/strings.xml\n"
            "--- a/res/values/strings.xml\n"
            "+++ b/res/values/strings.xml\n"
            "@@ -1 +1,4 @@\n"
            "+<string name=\"color_gamut\">Color gamut</string>\n"
            "+<string-array name=\"proxy_array\"><item>None</item></string-array>\n"
            "+<plurals name=\"ram_extender_size\"><item quantity=\"one\">1 GB</item></plurals>\n"
        )

        self.assertIn("color_gamut", facts["resource_keys"])
        self.assertIn("proxy_array", facts["resource_keys"])
        self.assertIn("ram_extender_size", facts["resource_keys"])

    def test_facts_from_diff_ignores_context_anchors_for_scope_evidence(self) -> None:
        module = load_patch_capture_module()

        facts = module.facts_from_diff(
            "diff --git a/device/product/system.prop b/device/product/system.prop\n"
            "--- a/device/product/system.prop\n"
            "+++ b/device/product/system.prop\n"
            "@@ -1,5 +1,6 @@\n"
            " ro.product.csk.control.pkg=com.iflytek.xirimiddleware \\\n"
            " ro.wifi.manufacturer=existing\n"
            " ro.wificlass=existing\n"
            "+persist.dlna.autostart=1\n"
            " debug.old.context=1\n"
            "diff --git a/res/values/strings.xml b/res/values/strings.xml\n"
            "--- a/res/values/strings.xml\n"
            "+++ b/res/values/strings.xml\n"
            "@@ -1,4 +1,5 @@\n"
            " <string name=\"unrelated_context_key\">Existing</string>\n"
            "+<string name=\"dlna_autostart_title\">DLNA autostart</string>\n"
        )

        self.assertEqual(facts["system_properties"], ["persist.dlna.autostart"])
        self.assertEqual(facts["resource_keys"], ["dlna_autostart_title"])

    def test_writes_verification_and_search_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            build_result_path = root / "build-result.json"
            build_result_path.write_text(
                json.dumps(
                    {
                        "result": "PASS",
                        "summary": "framework-minus-apex 编译通过",
                        "target": "framework-minus-apex",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260526-120000-patch",
                    "--platform",
                    "rk14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--implementation-origin",
                    "manual",
                    "--workflow-contract",
                    "manual_import",
                    "--status",
                    "validated",
                    "--verification",
                    "frameworks/base/services build PASS",
                    "--device",
                    "rk3576",
                    "--device-verification",
                    "Boot completed and navigation policy behavior matched expectation",
                    "--search-query",
                    "navigation policy toggle",
                    "--search-result",
                    "No reuse candidate found",
                    "--related-report-run-id",
                    "20260601-210000-daily",
                    "--build-result",
                    str(build_result_path),
                ],
                root,
            )
            package_dir = Path(json.loads(result.stdout)["package"])
            verification = json.loads((package_dir / "evidence" / "verification-result.json").read_text(encoding="utf-8"))
            build_result = json.loads((package_dir / "evidence" / "build-result.json").read_text(encoding="utf-8"))
            search = json.loads((package_dir / "evidence" / "search-before-change.json").read_text(encoding="utf-8"))
            diff_facts = json.loads((package_dir / "evidence" / "patch-diff-facts.json").read_text(encoding="utf-8"))
            problem_summary = json.loads((package_dir / "evidence" / "patch-problem-summary.json").read_text(encoding="utf-8"))
            risk_surface = json.loads((package_dir / "evidence" / "risk-surface.json").read_text(encoding="utf-8"))
            coding_check = json.loads((package_dir / "evidence" / "coding-standard-check.json").read_text(encoding="utf-8"))
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            evidence_ids = {item["id"] for item in manifest["evidence"]}

            self.assertEqual(verification["result"], "PASS")
            self.assertEqual(verification["method"], "device")
            self.assertEqual(verification["device"], "rk3576")
            self.assertEqual(verification["contract_version"], "akbs-verification-evidence/v2")
            self.assertEqual(verification["scope"], "feature")
            self.assertEqual(verification["requirement_acceptance"], "accepted")
            self.assertEqual(build_result["kind"], "build_result")
            self.assertEqual(build_result["result"], "PASS")
            self.assertEqual(search["result"], "INFO")
            self.assertEqual(search["queries"], ["navigation policy toggle"])
            self.assertEqual(diff_facts["kind"], "patch_diff_facts")
            self.assertRegex(diff_facts["content_sha1"], r"^[0-9a-f]{40}$")
            self.assertTrue(diff_facts["modified_files"])
            self.assertEqual(problem_summary["kind"], "patch_problem_summary")
            self.assertIn(problem_summary["confidence"], {"low", "medium", "high"})
            self.assertTrue(problem_summary["basis"])
            self.assertTrue(problem_summary["limits"])
            self.assertEqual(risk_surface["kind"], "risk_surface")
            self.assertTrue(risk_surface["risk_areas"])
            self.assertIn("patch-diff-facts", evidence_ids)
            self.assertIn("patch-problem-summary", evidence_ids)
            self.assertIn("risk-surface", evidence_ids)
            self.assertIn("verification-result", evidence_ids)
            self.assertIn("build-result", evidence_ids)
            self.assertIn("search-before-change", evidence_ids)
            self.assertRegex(manifest["patches"][0]["content_sha1"], r"^[0-9a-f]{40}$")
            self.assertEqual(manifest["related_report_run_ids"], ["20260601-210000-daily"])
            self.assertEqual(manifest["implementation_origin"], "manual")
            self.assertEqual(manifest["workflow_contract"], "manual_import")
            self.assertEqual(manifest["captured_by"], "codex")
            self.assertEqual(manifest["platform_token"], "rk14")
            self.assertEqual(manifest["platform"], "rk")
            self.assertEqual(manifest["android_version"], "14")
            self.assertTrue(manifest["coding_standard_check"]["required"])
            self.assertEqual(manifest["coding_standard_check"]["mode"], "capture_gate")
            self.assertEqual(manifest["patches"][0]["implementation_origin"], "manual")
            self.assertEqual(
                manifest["patches"][0]["workflow_contract"],
                "manual_import",
            )
            self.assertEqual(manifest["patches"][0]["platform"], "rk")
            self.assertEqual(manifest["patches"][0]["android_version"], "14")
            self.assertEqual(manifest["patches"][0]["reuse_hint"], True)
            self.assertNotIn("reusable", manifest["patches"][0])
            self.assertEqual(coding_check["implementation_origin"], "manual")
            self.assertTrue(coding_check["review_required"])

    def test_rejects_mode_only_patch_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_mode_only_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260615-120000-patch",
                    "--platform",
                    "mtk16",
                    "--feature",
                    "mode-only-noise",
                    "--summary",
                    "Ignore chmod-only diff noise",
                    "--status",
                    "candidate",
                ],
                root,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("只有文件权限变化", result.stderr or result.stdout)

    def test_filters_mode_only_sections_from_mixed_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _content_path, mode_noise_path = create_repo_with_mode_noise(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260615-121000-patch",
                    "--platform",
                    "mtk16",
                    "--feature",
                    "mixed-mode-noise",
                    "--summary",
                    "Keep content diff and ignore chmod-only noise",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            patch_path = package_dir / manifest["patches"][0]["path"]
            patch_text = patch_path.read_text(encoding="utf-8")
            changed = json.loads((package_dir / "evidence" / "changed-files.json").read_text(encoding="utf-8"))

            self.assertIn("DisplayPolicy.java", patch_text)
            self.assertNotIn("old mode 100755", patch_text)
            self.assertNotIn("new mode 100644", patch_text)
            self.assertNotIn(mode_noise_path.relative_to(root).as_posix(), patch_text)
            self.assertFalse(any(path.endswith("mode-noise.sh") for path in changed["modified_files"]))

    def test_validated_capture_requires_closed_search_decision_for_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260611-130000-patch",
                    "--workflow-contract",
                    "current_codex_skill",
                    "--platform",
                    "rk14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--status",
                    "validated",
                    "--verification",
                    "frameworks/base/services build PASS",
                    "--device",
                    "rk3576",
                    "--device-verification",
                    "Boot completed and navigation policy behavior matched expectation",
                    "--search-query",
                    "navigation policy toggle",
                    "--search-result",
                    "case-nav-policy matched modified files",
                ],
                root,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            errors = "\n".join(payload["local_check"]["errors"])
            self.assertIn("搜索使用决策", errors)
            self.assertIn("reuse/adapt/reference_only/not_applicable/not_found", errors)

    def test_codex_validated_capture_without_pre_change_search_blocks_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260611-131000-patch",
                    "--workflow-contract",
                    "current_codex_skill",
                    "--platform",
                    "rk14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--status",
                    "validated",
                    "--verification",
                    "frameworks/base/services build PASS",
                    "--device",
                    "rk3576",
                    "--device-verification",
                    "Boot completed and navigation policy behavior matched expectation",
                ],
                root,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            errors = "\n".join(payload["local_check"]["errors"])
            self.assertIn("开发前知识搜索", errors)
            self.assertIn("不能事后补造", errors)
            self.assertIn("保持真实工作流和实施来源", errors)
            self.assertNotIn("--implementation-origin manual", errors)

    def test_mixed_validated_capture_cannot_bypass_pre_change_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260611-131050-patch",
                    "--workflow-contract",
                    "current_codex_skill",
                    "--platform",
                    "rk14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--implementation-origin",
                    "mixed",
                    "--status",
                    "validated",
                    "--verification",
                    "frameworks/base/services build PASS",
                    "--device",
                    "rk3576",
                    "--device-verification",
                    "Boot completed and navigation policy behavior matched expectation",
                ],
                root,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            errors = "\n".join(
                json.loads(result.stdout)["local_check"]["errors"]
            )
            self.assertIn("current_codex_skill", errors)
            self.assertIn("保持真实工作流和实施来源", errors)
            self.assertNotIn("--implementation-origin manual", errors)

    def test_manual_validated_capture_allows_missing_pre_change_search_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260611-131100-patch",
                    "--platform",
                    "rk14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--implementation-origin",
                    "manual",
                    "--workflow-contract",
                    "manual_import",
                    "--status",
                    "validated",
                    "--verification",
                    "frameworks/base/services build PASS",
                    "--device",
                    "rk3576",
                    "--device-verification",
                    "Boot completed and navigation policy behavior matched expectation",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            search = json.loads((package_dir / "evidence" / "search-before-change.json").read_text(encoding="utf-8"))
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            package_check = json.loads((package_dir / "evidence" / "package-check.json").read_text(encoding="utf-8"))

            self.assertFalse(search["searched"])
            self.assertEqual(manifest["implementation_origin"], "manual")
            self.assertEqual(package_check["status"], "PASS")

    def test_rejects_generic_android_platform_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260611-130000-patch",
                    "--platform",
                    "android14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--status",
                    "candidate",
                ],
                root,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("不能使用泛化或非规范令牌", result.stderr or result.stdout)

    def test_normalizes_unisoc_platform_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260611-131000-patch",
                    "--platform",
                    "sprd14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["platform_token"], "unisoc14")
            self.assertEqual(manifest["platform"], "unisoc")
            self.assertEqual(manifest["android_version"], "14")
            self.assertTrue(manifest["patches"][0]["path"].startswith("patches/unisoc14-"))

    def test_writes_pre_change_reuse_decision_and_remote_to_local_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260611-120000-patch",
                    "--platform",
                    "rk14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--status",
                    "validated",
                    "--verification",
                    "frameworks/base/services build PASS",
                    "--device",
                    "rk3576",
                    "--device-verification",
                    "Boot completed and navigation policy behavior matched expectation",
                    "--search-query",
                    "navigation policy toggle",
                    "--search-result",
                    "case-nav-policy matched modified files but project differs",
                    "--reuse-decision",
                    "adapt",
                    "--reuse-target",
                    "case-nav-policy",
                    "--reuse-match",
                    "same WindowManager policy path",
                    "--reuse-mismatch",
                    "old variant is rk13, current project is TVE8402M on rk14",
                    "--reuse-reason",
                    "reuse case idea but produce a project-specific variant",
                    "--reuse-outcome",
                    "adapted_success",
                    "--remote-build-host",
                    "builder01",
                    "--remote-source-root",
                    "/build/android/TVE8402M",
                    "--remote-build-command",
                    "bash .codex/build-push.sh build --profile framework-services",
                    "--remote-build-profile",
                    "framework-services",
                    "--remote-artifact",
                    "/build/android/TVE8402M/out/target/product/tve8402m/system/framework/services.jar",
                    "--artifact-sha1",
                    "0123456789abcdef0123456789abcdef01234567",
                    "--artifact-transfer",
                    "scp builder01:/build/android/TVE8402M/out/target/product/tve8402m/system/framework/services.jar ~/.codex/artifacts/services.jar",
                    "--local-artifact",
                    str(root / "services.jar"),
                    "--adb-serial",
                    "ABC123",
                    "--adb-action",
                    "adb -s ABC123 push services.jar /system/framework/services.jar",
                    "--device-restart",
                    "adb -s ABC123 reboot",
                ],
                root,
            )
            package_dir = Path(json.loads(result.stdout)["package"])
            search = json.loads((package_dir / "evidence" / "search-before-change.json").read_text(encoding="utf-8"))
            verification = json.loads((package_dir / "evidence" / "verification-result.json").read_text(encoding="utf-8"))
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(search["reuse_decision"], "adapt")
            self.assertEqual(search["decision"], "adapt")
            self.assertEqual(search["targets"], ["case-nav-policy"])
            self.assertEqual(search["match_points"], ["same WindowManager policy path"])
            self.assertEqual(search["mismatch_points"], ["old variant is rk13, current project is TVE8402M on rk14"])
            self.assertEqual(search["reason"], "reuse case idea but produce a project-specific variant")
            self.assertEqual(search["outcome"], "adapted_success")
            self.assertEqual(verification["remote_build"]["host"], "builder01")
            self.assertEqual(verification["remote_build"]["source_root"], "/build/android/TVE8402M")
            self.assertEqual(verification["remote_build"]["profile"], "framework-services")
            self.assertEqual(verification["remote_build"]["artifacts"][0]["sha1"], "0123456789abcdef0123456789abcdef01234567")
            self.assertEqual(verification["local_delivery"]["transfer"], "scp builder01:/build/android/TVE8402M/out/target/product/tve8402m/system/framework/services.jar ~/.codex/artifacts/services.jar")
            self.assertEqual(verification["local_delivery"]["adb_serial"], "ABC123")
            self.assertIn("remote_build", manifest["verification_chain"])
            self.assertIn("local_delivery", manifest["verification_chain"])

    def test_auto_reads_remote_local_verification_evidence_from_source_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            evidence_dir = root / ".codex" / "evidence"
            evidence_dir.mkdir(parents=True)
            (evidence_dir / "latest-build-delivery.json").write_text(
                json.dumps(
                    {
                        "kind": "verification_result",
                        "result": "PASS",
                        "method": "device",
                        "summary": "remote build and local adb delivery passed",
                        "build": ["framework-services build PASS"],
                        "device": "ABC123",
                        "steps": ["boot completed after services.jar push"],
                        "remote_build": {
                            "host": "builder01",
                            "source_root": "/build/android/TVE8402M",
                            "command": "bash .codex/build-push.sh build --profile framework-services",
                            "profile": "framework-services",
                            "artifacts": [
                                {
                                    "path": "/build/android/TVE8402M/out/target/product/tve8402m/system/framework/services.jar",
                                    "sha1": "0123456789abcdef0123456789abcdef01234567",
                                }
                            ],
                        },
                        "local_delivery": {
                            "transfer": "scp builder01:/build/android/TVE8402M/out/target/product/tve8402m/system/framework/services.jar ~/.codex/artifacts/services.jar",
                            "local_artifacts": ["/mnt/c/Users/jinny/.codex/artifacts/services.jar"],
                            "adb_serial": "ABC123",
                            "adb_actions": ["adb -s ABC123 push services.jar /system/framework/services.jar"],
                            "device_restarts": ["adb -s ABC123 reboot"],
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260611-121500-patch",
                    "--platform",
                    "rk14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--status",
                    "candidate",
                    "--search-query",
                    "navigation policy toggle",
                    "--search-result",
                    "No reuse candidate found",
                    "--reuse-decision",
                    "not_found",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            verification = json.loads((package_dir / "evidence" / "verification-result.json").read_text(encoding="utf-8"))
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            readme = (package_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(verification["result"], "PASS")
            self.assertEqual(verification["method"], "device")
            self.assertEqual(verification["contract_version"], "akbs-verification-evidence/v2")
            self.assertEqual(verification["scope"], "build_delivery")
            self.assertEqual(verification["requirement_acceptance"], "unverified")
            self.assertEqual(verification["remote_build"]["host"], "builder01")
            self.assertEqual(verification["local_delivery"]["adb_serial"], "ABC123")
            self.assertIn("remote_build", manifest["verification_chain"])
            self.assertIn("local_delivery", manifest["verification_chain"])
            self.assertIn("builder01", readme)
            self.assertIn("/build/android/TVE8402M", readme)
            self.assertIn("0123456789abcdef0123456789abcdef01234567", readme)
            self.assertIn("ABC123", readme)
            self.assertIn("adb -s ABC123 push services.jar /system/framework/services.jar", readme)

    def test_validated_status_rejects_delivery_only_evidence(self) -> None:
        module = load_patch_capture_module()
        args = type("Args", (), {"status": "validated"})()
        payload = {
            "contract_version": "akbs-verification-evidence/v2",
            "scope": "build_delivery",
            "requirement_acceptance": "unverified",
            "result": "PASS",
            "method": "device",
            "build": ["framework-services build PASS"],
            "steps": ["adb push services.jar /system/framework/services.jar"],
        }

        errors = module.validate_verification_for_status(args, payload)

        self.assertTrue(any("需求级验收" in error for error in errors), errors)

    def test_common_framework_paths_produce_specific_patch_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_audio_camera_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260530-120000-patch",
                    "--platform",
                    "rk14",
                    "--feature",
                    "microphone-camera-permission",
                    "--summary",
                    "调整麦克风和相机权限回退策略",
                    "--status",
                    "candidate",
                ],
                root,
            )
            package_dir = Path(json.loads(result.stdout)["package"])
            diff_facts = json.loads((package_dir / "evidence" / "patch-diff-facts.json").read_text(encoding="utf-8"))
            problem_summary = json.loads((package_dir / "evidence" / "patch-problem-summary.json").read_text(encoding="utf-8"))
            risk_surface = json.loads((package_dir / "evidence" / "risk-surface.json").read_text(encoding="utf-8"))

            self.assertIn("Audio", diff_facts["modules"])
            self.assertIn("Camera", diff_facts["modules"])
            self.assertIn("音频录制", problem_summary["problem_summary"])
            self.assertIn("音频路由/音量行为", risk_surface["risk_areas"])
            self.assertIn("相机行为", risk_surface["risk_areas"])

    def test_launcher_capture_uses_explicit_problem_and_solution_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_launcher_repo(root)
            problem = "Launcher 工作区模式切换后，标签位置和裁切结果不符合产品要求。"
            solution = "调整 Workspace 布局与标签测量逻辑，并验证所有模式下的居中和完整显示。"
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260728-120000-launcher",
                    "--platform",
                    "rk14",
                    "--feature",
                    "launcher-workspace-label-layout",
                    "--summary",
                    "修复 Launcher 工作区模式切换后的标签居中和裁切",
                    "--problem-summary",
                    problem,
                    "--solution-summary",
                    solution,
                    "--status",
                    "candidate",
                ],
                root,
            )
            package_dir = Path(json.loads(result.stdout)["package"])
            payload = json.loads(
                (package_dir / "evidence" / "patch-problem-summary.json").read_text(encoding="utf-8")
            )

            self.assertEqual(payload["problem_summary"], problem)
            self.assertEqual(payload["solution_summary"], solution)
            self.assertEqual(payload["confidence"], "medium")
            self.assertIn("提交时显式提供了问题说明和方案说明", payload["basis"])

    def test_explicit_problem_and_solution_evidence_must_be_paired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_launcher_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260728-120000-launcher",
                    "--platform",
                    "rk14",
                    "--feature",
                    "launcher-workspace-label-layout",
                    "--summary",
                    "修复 Launcher 工作区模式切换后的标签居中和裁切",
                    "--problem-summary",
                    "Launcher 工作区标签显示不符合产品要求。",
                    "--status",
                    "candidate",
                ],
                root,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--problem-summary 和 --solution-summary 必须同时提供", result.stderr)

    def test_statusbar_paths_do_not_trigger_usb_semantics(self) -> None:
        patch_capture = load_patch_capture_module()
        files = [
            "src/com/android/systemui/statusbar/notification/stack/MediaContainerView.kt",
            "src/com/android/systemui/statusbar/notification/stack/NotificationStackScrollLayoutController.java",
            "src/com/android/systemui/keyguard/ui/view/layout/sections/DefaultMediaSection.kt",
        ]
        modules = patch_capture.modules_from_files(files)
        joined = " ".join(["SystemUI 锁屏媒体控件支持竖屏显示", " ".join(files), " ".join(modules)]).lower()
        flags = patch_capture.semantic_flags(joined, modules)
        problem, solution, _confidence = patch_capture.semantic_problem_solution(modules, flags)

        self.assertIn("SystemUI", modules)
        self.assertNotIn("USB", modules)
        self.assertFalse(flags["usb"])
        self.assertNotIn("USB", problem)
        self.assertNotIn("USB", solution)

    def test_usb_paths_still_trigger_usb_semantics(self) -> None:
        patch_capture = load_patch_capture_module()
        files = [
            "packages/SystemUI/src/com/android/systemui/usb/UsbPermissionActivity.java",
            "ueventd.rc",
        ]
        modules = patch_capture.modules_from_files(files)
        joined = " ".join(["云外设 App USB 权限自动获取", " ".join(files), " ".join(modules)]).lower()
        flags = patch_capture.semantic_flags(joined, modules)

        self.assertIn("USB", modules)
        self.assertTrue(flags["usb"])

    def test_external_evidence_rejects_unsupported_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            evidence_dir = root / "external-evidence"
            evidence_dir.mkdir()
            (evidence_dir / "random-note.json").write_text(
                json.dumps({"kind": "random_note", "result": "INFO"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260526-120000-patch",
                    "--platform",
                    "rk14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--status",
                    "candidate",
                    "--evidence-dir",
                    str(evidence_dir),
                ],
                root,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("外部 evidence kind 不支持", result.stderr or result.stdout)

    def test_validated_equivalent_verification_requires_reason_coverage_and_risk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)
            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260526-120000-patch",
                    "--platform",
                    "rk14",
                    "--feature",
                    "nav-policy-toggle",
                    "--summary",
                    "Allow navigation policy toggle",
                    "--status",
                    "validated",
                    "--verification-method",
                    "equivalent",
                    "--verification",
                    "static resource check PASS",
                ],
                root,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("equivalent", result.stdout)

    def test_infers_company_project_from_source_root_and_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "work" / "rk" / "TVA10A2R"
            root.mkdir(parents=True)
            create_plain_repo(root)
            run(["git", "checkout", "-b", "feature/TVA10A2R-camera-policy"], root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260604-120000-patch",
                    "--platform",
                    "mtk16",
                    "--feature",
                    "camera-policy",
                    "--summary",
                    "Camera2 reversePortrait direction compensation",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "TVA10A2R")
            self.assertEqual(manifest["patches"][0]["project"], "TVA10A2R")

    def test_non_company_project_argument_is_not_written_as_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_plain_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260604-130000-patch",
                    "--platform",
                    "mtk16",
                    "--feature",
                    "camera-policy",
                    "--summary",
                    "Camera2 reversePortrait direction compensation",
                    "--project",
                    "mtk android16 Camera2",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "unknown")
            self.assertEqual(manifest["patches"][0]["project"], "unknown")

    def test_confirmed_project_alias_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_plain_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260604-130500-patch",
                    "--platform",
                    "mtk16",
                    "--feature",
                    "camera-policy",
                    "--summary",
                    "Camera2 policy adjustment",
                    "--project",
                    "TVE8402",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "TVE8402M")
            self.assertEqual(manifest["patches"][0]["project"], "TVE8402M")

    def test_invalid_project_model_from_argument_is_not_recognized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_plain_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260604-130505-patch",
                    "--platform",
                    "mtk16",
                    "--feature",
                    "camera-policy",
                    "--summary",
                    "Camera2 policy adjustment",
                    "--project",
                    "TVE1234A",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "unknown")
            self.assertEqual(manifest["patches"][0]["project"], "unknown")

    def test_project_branch_suffix_is_normalized_to_project_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_plain_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260604-130510-patch",
                    "--platform",
                    "mtk15",
                    "--feature",
                    "usage-time-fix",
                    "--summary",
                    "TVE1067M1_H031 usage time fix",
                    "--project",
                    "TVE1067M1_H031",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "TVE1067M1")
            self.assertEqual(manifest["patches"][0]["project"], "TVE1067M1")
            self.assertEqual(manifest["project_inference"]["project"], "TVE1067M1")

    def test_nonstandard_project_suffix_is_kept_out_of_structured_project(self) -> None:
        examples = [
            ("TVE1086U_MAIN_HANGYAN", "TVE1086U"),
            ("TVE1091U福建移动高清", "TVE1091U"),
            ("TVA10A2R-camera-policy", "TVA10A2R"),
        ]
        for raw_project, expected_project in examples:
            with self.subTest(raw_project=raw_project):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    create_plain_repo(root)

                    result = run(
                        [
                            sys.executable,
                            str(SCRIPT),
                            "--source-root",
                            str(root),
                            "--out-dir",
                            "out",
                            "--run-id",
                            "20260604-130515-patch",
                            "--platform",
                            "mtk15",
                            "--feature",
                            "project-normalization",
                            "--summary",
                            f"{raw_project} project normalization",
                            "--project",
                            raw_project,
                            "--status",
                            "candidate",
                        ],
                        root,
                    )

                    package_dir = Path(json.loads(result.stdout)["package"])
                    manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

                    self.assertEqual(manifest["project"], expected_project)
                    self.assertEqual(manifest["patches"][0]["project"], expected_project)
                    self.assertEqual(manifest["project_inference"]["project"], expected_project)
                    self.assertIn(raw_project, " ".join(manifest["project_inference"]["raw_inputs"]))

    def test_tvi_project_model_from_argument_is_recognized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_plain_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260604-130520-patch",
                    "--platform",
                    "mtk15",
                    "--feature",
                    "camera-policy",
                    "--summary",
                    "Camera2 policy adjustment",
                    "--project",
                    "TVI3366R",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "TVI3366R")
            self.assertEqual(manifest["patches"][0]["project"], "TVI3366R")

    def test_tvi_arm_project_model_from_argument_is_recognized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_plain_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260604-130521-patch",
                    "--platform",
                    "rk90",
                    "--feature",
                    "industrial-policy",
                    "--summary",
                    "industrial policy adjustment",
                    "--project",
                    "TVI3315A",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "TVI3315A")
            self.assertEqual(manifest["platform"], "rk")
            self.assertEqual(manifest["patches"][0]["project"], "TVI3315A")

    def test_tvi_short_project_model_completes_with_chip_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_plain_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260604-130522-patch",
                    "--platform",
                    "rk90",
                    "--feature",
                    "industrial-policy",
                    "--summary",
                    "industrial policy adjustment",
                    "--project",
                    "TVI3315",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "TVI3315A")
            self.assertNotEqual(manifest["project"], "TVI3315R")
            self.assertEqual(manifest["platform"], "rk")
            self.assertEqual(manifest["patches"][0]["project"], "TVI3315A")

    def test_conflicting_project_clues_keep_project_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "work" / "rk" / "TVA10A2R"
            root.mkdir(parents=True)
            create_plain_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260604-131000-patch",
                    "--platform",
                    "mtk16",
                    "--feature",
                    "camera-policy",
                    "--summary",
                    "Camera2 reversePortrait direction compensation",
                    "--project",
                    "TVE1067M",
                    "--status",
                    "candidate",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "unknown")
            self.assertEqual(manifest["patches"][0]["project"], "unknown")
            self.assertEqual(manifest["project_inference"]["candidates"], ["TVA10A2R", "TVE1067M"])
            self.assertTrue(any("多个项目型号" in item for item in manifest["project_inference"]["limits"]))

    def test_multi_repo_feature_package_has_one_readme_and_multiple_patches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            frameworks_base = workspace / "android" / "frameworks" / "base"
            settings = workspace / "android" / "packages" / "apps" / "Settings"
            frameworks_base.mkdir(parents=True)
            settings.mkdir(parents=True)
            create_frameworks_base_repo(frameworks_base)
            create_settings_repo(settings)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(frameworks_base),
                    "--source-root",
                    str(settings),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260608-120000-feature",
                    "--platform",
                    "rk14",
                    "--feature",
                    "cross-repo-display-policy",
                    "--summary",
                    "跨源码仓库调整显示策略和设置入口",
                    "--status",
                    "candidate",
                ],
                workspace,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["package_type"], "framework_feature_patch")
            self.assertEqual(manifest["change_domain"], "framework")
            self.assertEqual(manifest["readme"], "README.md")
            self.assertEqual(len(manifest["patches"]), 2)
            self.assertEqual(
                {item["repo_path"] for item in manifest["patches"]},
                {"frameworks/base", "packages/apps/Settings"},
            )
            self.assertEqual(
                {Path(item["path"]).name for item in manifest["patches"]},
                {
                    "rk14-frameworks-base@cross-repo-display-policy.patch",
                    "rk14-settings@cross-repo-display-policy.patch",
                },
            )
            self.assertFalse(list((package_dir / "patches").glob("*.readme.md")))
            readme = (package_dir / "README.md").read_text(encoding="utf-8")
            self.assertIn("## 涉及源码仓库", readme)
            self.assertIn("frameworks/base", readme)
            self.assertIn("packages/apps/Settings", readme)
            self.assertIn("rk14-frameworks-base@cross-repo-display-policy.patch", readme)
            self.assertIn("rk14-settings@cross-repo-display-policy.patch", readme)
            self.assertIn("## 功能边界", readme)
            self.assertIn("功能目标: 跨源码仓库调整显示策略和设置入口", readme)
            self.assertIn("本子改动通过", readme)
            self.assertIn("共同服务上述功能目标", readme)

    def test_explicit_non_framework_domain_stays_a_local_android_capture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260831-120000-app-capture",
                    "--platform",
                    "rk14",
                    "--feature",
                    "app-policy-evidence",
                    "--summary",
                    "保存 App 领域修改材料",
                    "--project",
                    "TVE1067M",
                    "--status",
                    "candidate",
                    "--change-domain",
                    "app",
                ],
                root,
            )

            package_dir = Path(json.loads(result.stdout)["package"])
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            standard_check = json.loads(
                (package_dir / "evidence" / "coding-standard-check.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["package_type"], "android_feature_patch")
            self.assertEqual(manifest["change_domain"], "app")
            self.assertEqual(manifest["patches"][0]["change_domain"], "app")
            self.assertEqual(standard_check["policy_profile"], "app")
            self.assertEqual(standard_check["applied_policy_profiles"], ["universal_patch_archive"])

    def test_daily_bundle_summary_fails_function_scope_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260612-233425-feature",
                    "--platform",
                    "rk14",
                    "--feature",
                    "daily-bundle",
                    "--summary",
                    "TVE1086U 青鸾云 2026-06-12 今日补丁：HD 版本云电脑跳转逻辑、系统弹窗副屏显示、移除 F7/F8/F10/F12 功能按键、移除 Alt+Tab 最近任务组合键。",
                    "--status",
                    "candidate",
                ],
                root,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("按功能拆分", result.stderr)
            self.assertIn("一个补丁包只能对应一个共同功能目标", result.stderr)
            self.assertFalse((root / "out" / "20260612-233425-feature").exists())

    def test_unrelated_feature_collection_fails_before_package_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260615-215913-feature",
                    "--platform",
                    "unisoc14",
                    "--feature",
                    "mixed-window-video-miniapp",
                    "--summary",
                    "应用视窗设置、默认咪咕视频爱看版横屏全屏，以及爱奇艺小程序白边修复补丁包",
                    "--status",
                    "candidate",
                ],
                root,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("聚合包", result.stderr)
            self.assertIn("按功能拆分", result.stderr)
            self.assertFalse((root / "out" / "20260615-215913-feature").exists())

    def test_large_single_power_domain_summary_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260624-150200-feature",
                    "--platform",
                    "rk9",
                    "--feature",
                    "cmcc-power-screenoff-hibernate",
                    "--summary",
                    "按开关机.docx适配息屏/待机/亮屏/唤醒、电源弹窗和DevicePowerManager系统服务",
                    "--project",
                    "TVA10A2R",
                    "--status",
                    "candidate",
                ],
                root,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertTrue((root / "out" / "20260624-150200-feature").is_dir())

    def test_single_feature_summary_with_today_word_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260612-233500-feature",
                    "--platform",
                    "rk14",
                    "--feature",
                    "wifi-default-enable",
                    "--summary",
                    "今日完成 Wi-Fi 默认开启功能",
                    "--status",
                    "candidate",
                ],
                root,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["local_check"]["status"], "PASS")

    def test_rejects_output_under_plugin_skill_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_repo(root)

            result = run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-root",
                    str(root),
                    "--out-dir",
                    "out",
                    "--run-id",
                    "20260708-120000-feature",
                    "--platform",
                    "rk14",
                    "--feature",
                    "wifi-default-enable",
                    "--summary",
                    "今日完成 Wi-Fi 默认开启功能",
                    "--status",
                    "candidate",
                ],
                SKILL_DIR,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("不能写入插件 skill 源码目录", result.stderr)
            self.assertFalse((SKILL_DIR / "out" / "20260708-120000-feature").exists())


if __name__ == "__main__":
    unittest.main()
