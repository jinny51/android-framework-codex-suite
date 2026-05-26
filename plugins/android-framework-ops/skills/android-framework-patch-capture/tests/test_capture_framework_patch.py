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


class CaptureFrameworkPatchTests(unittest.TestCase):
    def test_writes_verification_and_search_evidence(self) -> None:
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
                ],
                root,
            )
            package_dir = Path(json.loads(result.stdout)["package"])
            verification = json.loads((package_dir / "evidence" / "verification-result.json").read_text(encoding="utf-8"))
            search = json.loads((package_dir / "evidence" / "search-before-change.json").read_text(encoding="utf-8"))
            diff_facts = json.loads((package_dir / "evidence" / "patch-diff-facts.json").read_text(encoding="utf-8"))
            problem_inference = json.loads((package_dir / "evidence" / "patch-problem-inference.json").read_text(encoding="utf-8"))
            risk_surface = json.loads((package_dir / "evidence" / "risk-surface.json").read_text(encoding="utf-8"))
            manifest = json.loads((package_dir / "manifest.json").read_text(encoding="utf-8"))
            evidence_ids = {item["id"] for item in manifest["evidence"]}

            self.assertEqual(verification["result"], "PASS")
            self.assertEqual(verification["method"], "device")
            self.assertEqual(verification["device"], "rk3576")
            self.assertEqual(search["result"], "INFO")
            self.assertEqual(search["queries"], ["navigation policy toggle"])
            self.assertEqual(diff_facts["kind"], "patch_diff_facts")
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
            self.assertIn("search-before-change", evidence_ids)

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
