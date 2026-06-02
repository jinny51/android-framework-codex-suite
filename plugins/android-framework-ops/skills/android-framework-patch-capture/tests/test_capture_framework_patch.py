from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "capture_framework_patch.py"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
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
        "  //gyf 20260526@ allow navigation policy toggle\n"
        "  static final String KEY = \"persist.sys.nav_policy\";\n"
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
        "  //gyf 20260530@ adjust microphone route fallback\n"
        "  static final String MIC_POLICY = \"persist.sys.mic_policy\";\n"
        "}\n",
        encoding="utf-8",
    )
    (camera / "CameraService.cpp").write_text(
        "class CameraService {\n"
        "  //gyf 20260530@ align camera permission fallback\n"
        "};\n",
        encoding="utf-8",
    )


class CaptureFrameworkPatchTests(unittest.TestCase):
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
                    "No reusable patch found",
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
            problem_inference = json.loads((package_dir / "evidence" / "patch-problem-inference.json").read_text(encoding="utf-8"))
            risk_surface = json.loads((package_dir / "evidence" / "risk-surface.json").read_text(encoding="utf-8"))
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            evidence_ids = {item["id"] for item in manifest["evidence"]}

            self.assertEqual(verification["result"], "PASS")
            self.assertEqual(verification["method"], "device")
            self.assertEqual(verification["device"], "rk3576")
            self.assertEqual(build_result["kind"], "build_result")
            self.assertEqual(build_result["result"], "PASS")
            self.assertEqual(search["result"], "INFO")
            self.assertEqual(search["queries"], ["navigation policy toggle"])
            self.assertEqual(diff_facts["kind"], "patch_diff_facts")
            self.assertRegex(diff_facts["content_sha1"], r"^[0-9a-f]{40}$")
            self.assertTrue(diff_facts["modified_files"])
            self.assertEqual(problem_inference["kind"], "patch_problem_inference")
            self.assertIn(problem_inference["confidence"], {"low", "medium", "high"})
            self.assertTrue(problem_inference["basis"])
            self.assertTrue(problem_inference["limits"])
            self.assertEqual(risk_surface["kind"], "risk_surface")
            self.assertTrue(risk_surface["risk_areas"])
            self.assertIn("patch-diff-facts", evidence_ids)
            self.assertIn("patch-problem-inference", evidence_ids)
            self.assertIn("risk-surface", evidence_ids)
            self.assertIn("verification-result", evidence_ids)
            self.assertIn("build-result", evidence_ids)
            self.assertIn("search-before-change", evidence_ids)
            self.assertRegex(manifest["patches"][0]["content_sha1"], r"^[0-9a-f]{40}$")
            self.assertEqual(manifest["related_report_run_ids"], ["20260601-210000-daily"])

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
            problem_inference = json.loads((package_dir / "evidence" / "patch-problem-inference.json").read_text(encoding="utf-8"))
            risk_surface = json.loads((package_dir / "evidence" / "risk-surface.json").read_text(encoding="utf-8"))

            self.assertIn("Audio", diff_facts["modules"])
            self.assertIn("Camera", diff_facts["modules"])
            self.assertIn("音频录制", problem_inference["inferred_problem"])
            self.assertIn("音频路由/音量行为", risk_surface["risk_areas"])
            self.assertIn("相机行为", risk_surface["risk_areas"])

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


if __name__ == "__main__":
    unittest.main()
