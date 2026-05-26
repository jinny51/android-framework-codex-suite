from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "android_knowledge_intake.py"
SPEC = importlib.util.spec_from_file_location("android_knowledge_intake", SCRIPT)
assert SPEC and SPEC.loader
intake = importlib.util.module_from_spec(SPEC)
sys.modules["android_knowledge_intake"] = intake
SPEC.loader.exec_module(intake)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_capture_package(root: Path, status: str = "validated") -> Path:
    package = root / "capture"
    patch = package / "patches" / "rk14-frameworks-base@nav-policy-toggle.patch"
    readme = package / "patches" / "rk14-frameworks-base@nav-policy-toggle.readme.md"
    patch.parent.mkdir(parents=True)
    patch.write_text(
        "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
        "--- a/frameworks/base/services/core/java/X.java\n"
        "+++ b/frameworks/base/services/core/java/X.java\n"
        "@@ -1 +1,2 @@\n"
        "+//gyf 20260526@ nav policy toggle\n",
        encoding="utf-8",
    )
    readme.write_text(
        "# nav policy toggle\n\n"
        "## 功能描述\n\nOK\n\n"
        "## 修改点\n\nOK\n\n"
        "## 日志控制\n\nOK\n\n"
        "## SystemProperties\n\nOK\n\n"
        "## 字符串国际化\n\nOK\n\n"
        "## 可回滚性\n\nOK\n",
        encoding="utf-8",
    )
    write_json(
        package / "evidence" / "verification-result.json",
        {
            "result": "PASS",
            "method": "device",
            "device": "rk3576",
            "steps": ["boot and verify nav behavior"],
        },
    )
    write_json(
        package / "evidence" / "search-before-change.json",
        {
            "result": "INFO",
            "method": "knowledge_search",
            "queries": ["nav policy"],
            "results": ["No reusable patch found"],
        },
    )
    write_json(
        package / "evidence" / "patch-diff-facts.json",
        {
            "kind": "patch_diff_facts",
            "modified_files": ["frameworks/base/services/core/java/X.java"],
            "modules": ["frameworks-base"],
            "symbols": [],
            "system_properties": ["persist.sys.nav_policy"],
            "settings_keys": [],
            "resource_keys": [],
            "framework_log_keys": [],
        },
    )
    write_json(
        package / "evidence" / "patch-problem-inference.json",
        {
            "kind": "patch_problem_inference",
            "confidence": "medium",
            "inferred_problem": "Navigation policy may not match product requirement",
            "inferred_solution": "Adjust framework policy path",
            "inferred_keywords": ["navigation", "policy"],
            "basis": ["patch modifies frameworks/base/services/core/java/X.java"],
            "limits": ["device verification is recorded separately"],
        },
    )
    write_json(
        package / "evidence" / "risk-surface.json",
        {
            "kind": "risk_surface",
            "confidence": "medium",
            "risk_areas": ["policy behavior"],
            "basis": ["patch modifies frameworks/base/services/core/java/X.java"],
            "limits": ["nearby regressions require separate verification"],
        },
    )
    write_json(
        package / "manifest.json",
        {
            "schema_version": "1.0",
            "package_type": "framework_patch",
            "project": "Android Framework",
            "summary": "Allow nav policy toggle",
            "status": status,
            "patches": [
                {
                    "path": "patches/rk14-frameworks-base@nav-policy-toggle.patch",
                    "readme": "patches/rk14-frameworks-base@nav-policy-toggle.readme.md",
                    "status": status,
                    "reusable": status in {"validated", "released"},
                    "project": "Android Framework",
                    "facts": {
                        "modified_files": ["frameworks/base/services/core/java/X.java"],
                        "system_properties": ["persist.sys.nav_policy"],
                        "settings_keys": [],
                        "resource_keys": [],
                        "framework_log_keys": [],
                    },
                }
            ],
            "evidence": [
                {
                    "id": "verification-result",
                    "kind": "verification_result",
                    "path": "evidence/verification-result.json",
                    "result": "PASS",
                    "summary": "device verification evidence",
                },
                {
                    "id": "search-before-change",
                    "kind": "search_before_change",
                    "path": "evidence/search-before-change.json",
                    "result": "INFO",
                    "summary": "pre-change search",
                },
                {
                    "id": "patch-diff-facts",
                    "kind": "patch_diff_facts",
                    "path": "evidence/patch-diff-facts.json",
                    "result": "INFO",
                    "summary": "patch facts",
                },
                {
                    "id": "patch-problem-inference",
                    "kind": "patch_problem_inference",
                    "path": "evidence/patch-problem-inference.json",
                    "result": "INFO",
                    "summary": "patch inference",
                },
                {
                    "id": "risk-surface",
                    "kind": "risk_surface",
                    "path": "evidence/risk-surface.json",
                    "result": "INFO",
                    "summary": "risk surface",
                },
            ],
        },
    )
    return package


def create_v2_patch_incoming(
    root: Path,
    *,
    quality: str = "candidate",
    facts: dict | None = None,
    evidence_payload: dict | None = None,
) -> tuple[Path, dict]:
    package = root / "incoming"
    patch = package / "patches" / "rk14-frameworks-base@nav-policy-toggle.patch"
    readme = package / "patches" / "rk14-frameworks-base@nav-policy-toggle.readme.md"
    patch.parent.mkdir(parents=True)
    patch.write_text(
        "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
        "--- a/frameworks/base/services/core/java/X.java\n"
        "+++ b/frameworks/base/services/core/java/X.java\n"
        "@@ -1 +1,2 @@\n"
        "+//gyf 20260526@ nav policy toggle\n",
        encoding="utf-8",
    )
    readme.write_text("# nav policy toggle\n", encoding="utf-8")
    evidence = []
    if evidence_payload is not None:
        evidence_path = package / "evidence" / "analysis.json"
        write_json(evidence_path, evidence_payload)
        evidence = [
            {
                "id": "analysis",
                "kind": evidence_payload.get("kind"),
                "path": "evidence/analysis.json",
                "result": "INFO",
            }
        ]
    manifest = {
        "schema_version": "2.0",
        "package_kind": "patch_contribution",
        "channel": "strict",
        "quality": quality,
        "member": "jinny",
        "date": "2026-05-26",
        "run_id": "20260526-120000-patch",
        "project": "Android Framework",
        "summary": "Allow nav policy toggle",
        "source": {},
        "reports": [],
        "patches": [
            {
                "id": "patch-main",
                "path": "patches/rk14-frameworks-base@nav-policy-toggle.patch",
                "readme": "patches/rk14-frameworks-base@nav-policy-toggle.readme.md",
                "facts": facts if facts is not None else {"modified_files": ["frameworks/base/services/core/java/X.java"]},
            }
        ],
        "evidence": evidence,
        "relations": [],
        "quality_claims": {},
    }
    return package, manifest


class PatchCaptureIngestTests(unittest.TestCase):
    def test_v2_patch_package_preserves_capture_evidence_and_quality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = create_capture_package(root)
            config = {
                "member_alias": "jinny",
                "member_name": "Wu Jinny",
                "out_dir": str(root / "out"),
                "repo_url": "test35:/home/test35/work/knowledge/remote.git",
                "max_attachment_mb": "5",
                "timezone": "Asia/Shanghai",
                "synthetic_data": "false",
            }
            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                config,
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(capture)],
                project="Android Framework",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="2.0",
            )
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))

            self.assertEqual(check["status"], "PASS")
            self.assertEqual(manifest["quality"], "validated")
            self.assertEqual(manifest["patches"][0]["facts"]["modified_files"], ["frameworks/base/services/core/java/X.java"])
            evidence_ids = {item["id"] for item in manifest["evidence"]}
            self.assertIn("capture-verification-result", evidence_ids)
            self.assertIn("capture-search-before-change", evidence_ids)
            self.assertIn("capture-patch-diff-facts", evidence_ids)
            self.assertIn("capture-patch-problem-inference", evidence_ids)
            self.assertIn("capture-risk-surface", evidence_ids)
            self.assertTrue((package / "evidence" / "capture-verification-result.json").is_file())
            self.assertTrue((package / "evidence" / "capture-search-before-change.json").is_file())
            self.assertTrue((package / "evidence" / "capture-patch-diff-facts.json").is_file())
            self.assertTrue((package / "evidence" / "capture-patch-problem-inference.json").is_file())
            self.assertTrue((package / "evidence" / "capture-risk-surface.json").is_file())

    def test_local_v2_validation_rejects_validated_without_pass_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = root / "incoming"
            (package / "patches").mkdir(parents=True)
            (package / "evidence").mkdir()
            (package / "patches" / "rk14-frameworks-base@nav-policy-toggle.patch").write_text("diff --git a/X.java b/X.java\n", encoding="utf-8")
            (package / "patches" / "rk14-frameworks-base@nav-policy-toggle.readme.md").write_text("# readme\n", encoding="utf-8")
            write_json(package / "evidence" / "verification-result.json", {"result": "INFO", "method": "not_provided"})
            manifest = {
                "schema_version": "2.0",
                "package_kind": "patch_contribution",
                "channel": "strict",
                "quality": "validated",
                "member": "jinny",
                "date": "2026-05-26",
                "run_id": "20260526-120000-patch",
                "project": "Android Framework",
                "summary": "Allow nav policy toggle",
                "source": {},
                "reports": [],
                "patches": [
                    {
                        "id": "patch-main",
                        "path": "patches/rk14-frameworks-base@nav-policy-toggle.patch",
                        "readme": "patches/rk14-frameworks-base@nav-policy-toggle.readme.md",
                        "facts": {"modified_files": ["X.java"]},
                    }
                ],
                "evidence": [
                    {
                        "id": "verification-result",
                        "kind": "verification_result",
                        "path": "evidence/verification-result.json",
                        "result": "INFO",
                    }
                ],
                "relations": [],
                "quality_claims": {
                    "risk_notes": "risk",
                    "rollback_notes": "rollback",
                    "scope": "scope",
                },
            }

            result = intake.validate_v2_package(package, manifest)

            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("PASS" in error for error in result["errors"]))

    def test_local_v2_validation_accepts_imported_strict_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package, manifest = create_v2_patch_incoming(Path(tmp), quality="imported")

            result = intake.validate_v2_package(package, manifest)

            self.assertEqual(result["status"], "PASS")

    def test_local_v2_validation_derives_missing_modified_files_from_patch_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package, manifest = create_v2_patch_incoming(Path(tmp), facts={})

            result = intake.validate_v2_package(package, manifest)

            self.assertEqual(result["status"], "PASS")
            self.assertTrue(any("反推" in warning for warning in result["warnings"]))

    def test_local_v2_validation_rejects_inference_without_basis_or_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            package, manifest = create_v2_patch_incoming(
                Path(tmp),
                evidence_payload={
                    "kind": "patch_problem_inference",
                    "confidence": "certain",
                    "inferred_problem": "Navigation behavior changed",
                    "basis": [],
                    "limits": [],
                },
            )

            result = intake.validate_v2_package(package, manifest)

            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("confidence" in error for error in result["errors"]))
            self.assertTrue(any("basis" in error for error in result["errors"]))
            self.assertTrue(any("limits" in error for error in result["errors"]))

    def test_candidate_capture_package_does_not_become_validated_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = create_capture_package(root, status="candidate")
            config = {
                "member_alias": "jinny",
                "member_name": "Wu Jinny",
                "out_dir": str(root / "out"),
                "repo_url": "test35:/home/test35/work/knowledge/remote.git",
                "max_attachment_mb": "5",
                "timezone": "Asia/Shanghai",
                "synthetic_data": "false",
            }
            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                config,
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(capture)],
                project="Android Framework",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="2.0",
            )
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["patches"][0]["status"], "candidate")
            self.assertEqual(manifest["quality"], "candidate")


if __name__ == "__main__":
    unittest.main()
