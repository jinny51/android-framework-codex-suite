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


def valid_patch_readme(title: str = "nav policy toggle") -> str:
    return (
        f"# {title}\n\n"
        "## 功能描述\n\n"
        "调整 Framework 导航策略开关，适用于项目验证后的策略复用。\n\n"
        "## 修改点\n\n"
        "- 修改 frameworks/base/services/core/java/X.java 中的策略判断。\n\n"
        "## 日志控制\n\n"
        "无新增运行时日志。\n\n"
        "## SystemProperties\n\n"
        "无新增系统属性。\n\n"
        "## 字符串国际化\n\n"
        "无新增字符串资源。\n\n"
        "## 可回滚性\n\n"
        "回滚该 patch 后恢复原导航策略。\n"
    )


def create_capture_package(
    root: Path,
    status: str = "validated",
    related_report_run_ids: list[str] | None = None,
    include_build_result: bool = False,
) -> Path:
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
    readme.write_text(valid_patch_readme(), encoding="utf-8")
    write_json(package / "evidence" / "verification-result.json", {"result": "PASS", "method": "device", "summary": "device pass"})
    write_json(package / "evidence" / "search-before-change.json", {"result": "INFO", "method": "knowledge_search", "queries": ["nav policy"]})
    if include_build_result:
        write_json(
            package / "evidence" / "build-result.json",
            {
                "kind": "build_result",
                "result": "PASS",
                "summary": "framework-minus-apex 编译通过",
                "target": "framework-minus-apex",
            },
        )
    write_json(
        package / "evidence" / "patch-diff-facts.json",
        {
            "kind": "patch_diff_facts",
            "modified_files": ["frameworks/base/services/core/java/X.java"],
            "modules": ["frameworks-base"],
            "symbols": [],
        },
    )
    write_json(
        package / "evidence" / "patch-problem-summary.json",
        {
            "kind": "patch_problem_summary",
            "confidence": "medium",
            "problem_summary": "Navigation policy may need adjustment",
            "solution_summary": "Adjust framework policy path",
            "basis": ["patch modifies frameworks/base/services/core/java/X.java"],
            "limits": ["verification is separate"],
        },
    )
    write_json(
        package / "evidence" / "risk-surface.json",
        {
            "kind": "risk_surface",
            "confidence": "medium",
            "risk_areas": ["policy behavior"],
            "basis": ["patch modifies frameworks/base/services/core/java/X.java"],
            "limits": ["nearby regressions require verification"],
        },
    )
    manifest = {
        "schema_version": "1.0",
        "package_type": "framework_patch",
        "project": "TVE1234A",
        "summary": "Allow nav policy toggle",
        "status": status,
        "patches": [
            {
                "path": "patches/rk14-frameworks-base@nav-policy-toggle.patch",
                "readme": "patches/rk14-frameworks-base@nav-policy-toggle.readme.md",
                "status": status,
                "reusable": status == "validated",
                "project": "TVE1234A",
                "facts": {"modified_files": ["frameworks/base/services/core/java/X.java"]},
            }
        ],
        "evidence": [
            {"id": "verification-result", "kind": "verification_result", "path": "evidence/verification-result.json", "result": "PASS"},
            {"id": "search-before-change", "kind": "search_before_change", "path": "evidence/search-before-change.json", "result": "INFO"},
            {"id": "patch-diff-facts", "kind": "patch_diff_facts", "path": "evidence/patch-diff-facts.json", "result": "INFO"},
            {"id": "patch-problem-summary", "kind": "patch_problem_summary", "path": "evidence/patch-problem-summary.json", "result": "INFO"},
            {"id": "risk-surface", "kind": "risk_surface", "path": "evidence/risk-surface.json", "result": "INFO"},
        ],
    }
    if include_build_result:
        manifest["evidence"].append(
            {
                "id": "build-result",
                "kind": "build_result",
                "path": "evidence/build-result.json",
                "result": "PASS",
                "summary": "framework-minus-apex 编译通过",
            }
        )
    if related_report_run_ids:
        manifest["related_report_run_ids"] = related_report_run_ids
    write_json(package / "manifest.json", manifest)
    return package


class PatchCaptureIngestTests(unittest.TestCase):
    def config(self, root: Path) -> dict[str, str]:
        return {
            "member_alias": "admin_alias",
            "member_name": "管理员姓名",
            "out_dir": str(root / "out"),
            "repo_url": "test35:/home/test35/work/knowledge/remote.git",
            "max_attachment_mb": "5",
            "timezone": "Asia/Shanghai",
            "synthetic_data": "false",
        }

    def test_capture_package_generates_framework_change_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root, related_report_run_ids=["20260601-210000-daily"]))],
                project="TVE1234A",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))
            diff_facts = json.loads((package / "knowledge" / "evidence" / "patch_diff_facts.json").read_text(encoding="utf-8"))
            source = json.loads((package / "knowledge" / "evidence" / "source.json").read_text(encoding="utf-8"))
            problem = json.loads((package / "knowledge" / "evidence" / "capture" / "capture-patch-problem-summary.json").read_text(encoding="utf-8"))
            risk = json.loads((package / "knowledge" / "evidence" / "capture" / "capture-risk-surface.json").read_text(encoding="utf-8"))

            self.assertEqual(check["status"], "PASS")
            self.assertEqual(manifest["schema"], "knowledge-incoming-package")
            self.assertEqual(manifest["schema_version"], "1")
            self.assertEqual(manifest["package_kind"], "framework_change")
            self.assertEqual(manifest["member_alias"], "admin_alias")
            self.assertEqual(manifest["maturity"], "validated")
            self.assertEqual(manifest["platform"], "rk")
            self.assertEqual(manifest["android_version"], "14")
            self.assertEqual(manifest["related_report_run_ids"], ["20260601-210000-daily"])
            self.assertRegex(diff_facts["payload"]["content_sha1"], r"^[0-9a-f]{40}$")
            self.assertEqual(diff_facts["payload"]["content_sha1"], diff_facts["payload"]["patches"][0]["content_sha1"])
            for evidence in (source, problem, risk):
                self.assertEqual(evidence["case_id"], manifest["case_id"])
                self.assertEqual(evidence["variant_id"], manifest["variant_id"])
            self.assertNotIn("package_path", source["payload"])
            self.assertNotIn("manifest_path", source["payload"])
            self.assertNotIn("cwd", source["payload"])
            self.assertNotIn("host", source["payload"])
            evidence_files = set(manifest["files"]["evidence"])
            self.assertIn("knowledge/evidence/source.json", evidence_files)
            self.assertIn("knowledge/evidence/project_inference.json", evidence_files)
            self.assertIn("knowledge/evidence/verification_result.json", evidence_files)

    def test_capture_package_preserves_optional_build_result_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root, include_build_result=True))],
                project="TVE1234A",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            evidence_files = set(manifest["files"]["evidence"])
            self.assertIn("knowledge/evidence/capture/capture-build-result.json", evidence_files)

            build_result = json.loads((package / "knowledge" / "evidence" / "capture" / "capture-build-result.json").read_text(encoding="utf-8"))
            self.assertEqual(build_result["kind"], "build_result")
            self.assertEqual(build_result["result"], "PASS")
            self.assertEqual(build_result["case_id"], manifest["case_id"])
            self.assertEqual(build_result["variant_id"], manifest["variant_id"])

    def test_blocked_patch_stays_blocked_without_becoming_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch = root / "mtk15-frameworks-base@blocked-policy.patch"
            patch.write_text(
                "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
                "--- a/frameworks/base/services/core/java/X.java\n"
                "+++ b/frameworks/base/services/core/java/X.java\n"
                "@@ -1 +1,2 @@\n"
                "+//gyf 20260526@ blocked policy investigation\n",
                encoding="utf-8",
            )

            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-130000-patch",
                patch_paths=[str(patch)],
                patch_package_paths=[],
                project="TVE1234A",
                summary="Blocked policy investigation",
                status="blocked",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            variant = json.loads((package / "knowledge" / "variant.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["maturity"], "blocked")
            self.assertEqual(variant["status"], "blocked")

    def test_standalone_patch_with_empty_readme_fails_local_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch = root / "rk14-frameworks-base@empty-readme.patch"
            patch.write_text(
                "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
                "--- a/frameworks/base/services/core/java/X.java\n"
                "+++ b/frameworks/base/services/core/java/X.java\n"
                "@@ -1 +1,2 @@\n"
                "+//gyf 20260526@ empty readme case\n",
                encoding="utf-8",
            )
            patch.with_suffix(".readme.md").write_text("", encoding="utf-8")

            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-140000-patch",
                patch_paths=[str(patch)],
                patch_package_paths=[],
                project="TVE1234A",
                summary="Empty readme case",
                status="candidate",
                schema_version="1",
            )

            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))
            self.assertEqual(check["status"], "FAIL")
            self.assertTrue(any("readme" in item and "不能为空" in item for item in check["errors"]))

    def test_standalone_patch_with_template_readme_fails_local_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch = root / "rk14-frameworks-base@template-readme.patch"
            patch.write_text(
                "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
                "--- a/frameworks/base/services/core/java/X.java\n"
                "+++ b/frameworks/base/services/core/java/X.java\n"
                "@@ -1 +1,2 @@\n"
                "+//gyf 20260526@ template readme case\n",
                encoding="utf-8",
            )
            patch.with_suffix(".readme.md").write_text(
                intake.patch_readme_template(
                    intake.PatchInfo(path=patch, name=patch.name, project="TVE1234A"),
                    self.config(root),
                ),
                encoding="utf-8",
            )

            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-150000-patch",
                patch_paths=[str(patch)],
                patch_package_paths=[],
                project="TVE1234A",
                summary="Template readme case",
                status="candidate",
                schema_version="1",
            )

            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))
            self.assertEqual(check["status"], "FAIL")
            self.assertTrue(any("readme" in item and "TODO" in item for item in check["errors"]))

    def test_candidate_capture_package_does_not_become_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root, status="candidate"))],
                project="TVE1234A",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["maturity"], "candidate")

    def test_standalone_patch_without_verification_is_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch = root / "rk14-frameworks-base@nav-policy-toggle.patch"
            patch.write_text(
                "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
                "--- a/frameworks/base/services/core/java/X.java\n"
                "+++ b/frameworks/base/services/core/java/X.java\n"
                "@@ -1 +1,2 @@\n"
                "+//gyf 20260526@ nav policy toggle\n",
                encoding="utf-8",
            )

            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[str(patch)],
                patch_package_paths=[],
                project="unknown",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            verification = json.loads((package / "knowledge" / "evidence" / "verification_result.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["maturity"], "candidate")
            self.assertEqual(verification["payload"]["result"], "MISSING")

    def test_chinese_summary_produces_distinct_framework_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_patch = root / "mtk15-frameworks-base@volume-dialog-position.patch"
            second_patch = root / "mtk15-frameworks-base@statusbar-policy.patch"
            for patch in (first_patch, second_patch):
                patch.write_text(
                    "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
                    "--- a/frameworks/base/services/core/java/X.java\n"
                    "+++ b/frameworks/base/services/core/java/X.java\n"
                    "@@ -1 +1,2 @@\n"
                    "+//gyf 20260601@ framework policy\n",
                    encoding="utf-8",
                )
                patch.with_suffix(".readme.md").write_text(valid_patch_readme(patch.stem), encoding="utf-8")

            first = intake.prepare_patch_package(
                dt.date(2026, 6, 1),
                self.config(root),
                run_id="20260601-120000-first",
                patch_paths=[str(first_patch)],
                patch_package_paths=[],
                project="TVE8402M",
                summary="通知栏音量弹窗位置适配",
                status="candidate",
                schema_version="1",
            )
            second = intake.prepare_patch_package(
                dt.date(2026, 6, 1),
                self.config(root),
                run_id="20260601-120000-second",
                patch_paths=[str(second_patch)],
                patch_package_paths=[],
                project="TVE8402M",
                summary="状态栏策略调整",
                status="candidate",
                schema_version="1",
            )

            first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
            second_manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))

            self.assertNotEqual(first_manifest["case_id"], second_manifest["case_id"])
            self.assertNotEqual(first_manifest["variant_id"], second_manifest["variant_id"])
            self.assertNotEqual(first_manifest["case_id"], "case-item")
            self.assertNotEqual(first_manifest["variant_id"], "variant-mtk-15-tve8402m")
            self.assertRegex(first_manifest["case_id"], r"^case-framework-change-[0-9a-f]{10}$")
            self.assertRegex(first_manifest["variant_id"], r"^variant-mtk-15-tve8402m-[0-9a-f]{10}$")

    def test_patch_semantics_still_identify_common_framework_paths(self) -> None:
        files = [
            "services/core/java/com/android/server/audio/AudioService.java",
            "frameworks/av/services/camera/libcameraservice/CameraService.cpp",
            "modules/rockchip_apps.mk",
        ]
        modules = intake.patch_modules_from_files(files)
        problem, risk = intake.patch_problem_and_risk_payloads(
            "patch-main",
            "patches/rk14-frameworks-base@media-camera.patch",
            "调整麦克风、相机权限和预置应用策略",
            {"modified_files": files, "modules": modules, "symbols": []},
        )

        self.assertIn("Audio", modules)
        self.assertIn("Camera", modules)
        self.assertIn("ProductConfig", modules)
        self.assertIn("音频录制", problem["problem_summary"])
        self.assertIn("音频路由/音量行为", risk["risk_areas"])
        self.assertIn("相机行为", risk["risk_areas"])
        self.assertIn("产品配置/预置应用", risk["risk_areas"])

    def test_project_inference_keeps_full_model_and_base_model(self) -> None:
        project, payload = intake.infer_project(
            "unknown",
            [{"project": "TVE1067M1_H031", "path": "patches/mtk16-settings@lockscreen.patch"}],
            [],
            "",
        )

        self.assertEqual(project, "TVE1067M1_H031")
        self.assertEqual(payload["base_model"], "TVE1067M")
        self.assertEqual(payload["suffix"], "1_H031")
        self.assertTrue(payload["company_rule_match"])


if __name__ == "__main__":
    unittest.main()
