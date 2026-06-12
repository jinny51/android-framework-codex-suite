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
    project: str = "TVE1234A",
    source_root: str | None = None,
    git_branch: str = "",
    git_remote: str = "",
    search_payload: dict | None = None,
) -> Path:
    package = root / "capture"
    patch = package / "patches" / "rk14-frameworks-base@nav-policy-toggle.patch"
    readme = package / "README.md"
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
    write_json(
        package / "evidence" / "search-before-change.json",
        search_payload
        if search_payload is not None
        else {"result": "INFO", "method": "knowledge_search", "queries": ["nav policy"], "searched": True},
    )
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
        "schema_version": "2.0",
        "package_type": "framework_feature_patch",
        "feature": "nav-policy-toggle",
        "readme": "README.md",
        "project": project,
        "platform_token": "rk14",
        "platform": "rk",
        "android_version": "14",
        "summary": "Allow nav policy toggle",
        "status": status,
        "implementation_origin": "manual",
        "captured_by": "codex",
        "coding_standard_check": {
            "required": True,
            "mode": "capture_gate",
            "path": "evidence/coding-standard-check.json",
            "result": "PASS",
        },
        "git_repositories": [
            {
                "repo_path": "frameworks/base",
                "root": source_root or "/work/android/frameworks/base",
                "git": {"branch": git_branch, "remote": git_remote},
            }
        ],
        "patches": [
            {
                "id": "rk14-frameworks-base@nav-policy-toggle",
                "path": "patches/rk14-frameworks-base@nav-policy-toggle.patch",
                "repo_path": "frameworks/base",
                "source_root": source_root or "/work/android/frameworks/base",
                "status": status,
                "reuse_hint": status == "validated",
                "project": project,
                "platform_token": "rk14",
                "platform": "rk",
                "android_version": "14",
                "implementation_origin": "manual",
                "captured_by": "codex",
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


def create_feature_capture_package(root: Path) -> Path:
    package = root / "feature-capture"
    patch_dir = package / "patches"
    patch_dir.mkdir(parents=True)
    readme = package / "README.md"
    readme.write_text(valid_patch_readme("cross repo display policy"), encoding="utf-8")
    first_patch = patch_dir / "rk14-frameworks-base@cross-repo-display-policy.patch"
    second_patch = patch_dir / "rk14-settings@cross-repo-display-policy.patch"
    first_patch.write_text(
        "diff --git a/services/core/java/com/android/server/wm/DisplayPolicy.java b/services/core/java/com/android/server/wm/DisplayPolicy.java\n"
        "--- a/services/core/java/com/android/server/wm/DisplayPolicy.java\n"
        "+++ b/services/core/java/com/android/server/wm/DisplayPolicy.java\n"
        "@@ -1 +1,2 @@\n"
        "+//gyf 20260608@ display policy\n",
        encoding="utf-8",
    )
    second_patch.write_text(
        "diff --git a/src/com/android/settings/DisplaySettings.java b/src/com/android/settings/DisplaySettings.java\n"
        "--- a/src/com/android/settings/DisplaySettings.java\n"
        "+++ b/src/com/android/settings/DisplaySettings.java\n"
        "@@ -1 +1,2 @@\n"
        "+//gyf 20260608@ settings entry\n",
        encoding="utf-8",
    )
    write_json(package / "evidence" / "verification-result.json", {"result": "PASS", "method": "device", "summary": "device pass"})
    write_json(package / "evidence" / "search-before-change.json", {"result": "INFO", "method": "knowledge_search", "queries": ["display policy"]})
    write_json(
        package / "evidence" / "patch-problem-summary.json",
        {
            "kind": "patch_problem_summary",
            "scope": "feature",
            "confidence": "medium",
            "problem_summary": "显示策略和设置入口需要一起适配。",
            "solution_summary": "同时调整 Framework 策略和 Settings 入口。",
            "basis": ["功能包包含 frameworks/base 和 packages/apps/Settings 两个源码仓库补丁"],
            "limits": ["设备验证记录独立保存"],
        },
    )
    write_json(
        package / "evidence" / "risk-surface.json",
        {
            "kind": "risk_surface",
            "scope": "feature",
            "confidence": "medium",
            "risk_areas": ["显示策略", "设置入口"],
            "basis": ["功能包包含两个源码仓库补丁"],
            "limits": ["跨仓库变更需要整体验证"],
        },
    )
    manifest = {
        "schema_version": "2.0",
        "package_type": "framework_feature_patch",
        "feature": "cross-repo-display-policy",
        "readme": "README.md",
        "project": "TVE1234A",
        "platform_token": "rk14",
        "platform": "rk",
        "android_version": "14",
        "summary": "跨源码仓库调整显示策略和设置入口",
        "status": "validated",
        "implementation_origin": "manual",
        "captured_by": "codex",
        "coding_standard_check": {
            "required": True,
            "mode": "capture_gate",
            "path": "evidence/coding-standard-check.json",
            "result": "PASS",
        },
        "source_roots": ["/work/android/frameworks/base", "/work/android/packages/apps/Settings"],
        "git_repositories": [
            {"repo_path": "frameworks/base", "root": "/work/android/frameworks/base", "git": {"branch": "main", "remote": ""}},
            {"repo_path": "packages/apps/Settings", "root": "/work/android/packages/apps/Settings", "git": {"branch": "main", "remote": ""}},
        ],
        "patches": [
            {
                "id": "rk14-frameworks-base@cross-repo-display-policy",
                "path": "patches/rk14-frameworks-base@cross-repo-display-policy.patch",
                "repo_path": "frameworks/base",
                "source_root": "/work/android/frameworks/base",
                "status": "validated",
                "reuse_hint": True,
                "project": "TVE1234A",
                "platform_token": "rk14",
                "platform": "rk",
                "android_version": "14",
                "implementation_origin": "manual",
                "captured_by": "codex",
                "facts": {"modified_files": ["services/core/java/com/android/server/wm/DisplayPolicy.java"], "modules": ["frameworks-base"]},
            },
            {
                "id": "rk14-settings@cross-repo-display-policy",
                "path": "patches/rk14-settings@cross-repo-display-policy.patch",
                "repo_path": "packages/apps/Settings",
                "source_root": "/work/android/packages/apps/Settings",
                "status": "validated",
                "reuse_hint": True,
                "project": "TVE1234A",
                "platform_token": "rk14",
                "platform": "rk",
                "android_version": "14",
                "implementation_origin": "manual",
                "captured_by": "codex",
                "facts": {"modified_files": ["src/com/android/settings/DisplaySettings.java"], "modules": ["settings"]},
            },
        ],
        "evidence": [
            {"id": "verification-result", "kind": "verification_result", "path": "evidence/verification-result.json", "result": "PASS", "scope": "feature"},
            {"id": "search-before-change", "kind": "search_before_change", "path": "evidence/search-before-change.json", "result": "INFO", "scope": "feature"},
            {"id": "patch-problem-summary", "kind": "patch_problem_summary", "path": "evidence/patch-problem-summary.json", "result": "INFO", "scope": "feature"},
            {"id": "risk-surface", "kind": "risk_surface", "path": "evidence/risk-surface.json", "result": "INFO", "scope": "feature"},
        ],
    }
    write_json(package / "manifest.json", manifest)
    return package


def write_member_search_usage(out_dir: Path, date: str, decision: str = "adapt") -> Path:
    record_dir = out_dir / "search-usage" / date.replace("-", "")
    record_dir.mkdir(parents=True, exist_ok=True)
    path = record_dir / f"{date.replace('-', '')}-usage.json"
    path.write_text(
        json.dumps(
            {
                "schema": "android-knowledge-search-usage",
                "schema_version": "1",
                "created_at": f"{date}T09:30:00+08:00",
                "date": date,
                "profile": "member01",
                "member_alias": "admin_alias",
                "query": "显示策略 split screen",
                "type": "all",
                "searched": True,
                "decision": decision,
                "reuse_decision": decision,
                "targets": ["case-display-policy"],
                "match_points": ["同类显示策略"],
                "mismatch_points": ["项目源码路径不同"],
                "reason": "复用思路但需要适配当前项目",
                "outcome": "not_started",
                "result_count": 1,
                "results": [{"kind": "case", "id": "case-display-policy", "title": "显示策略"}],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


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
            diff_facts = json.loads((package / "materials" / "evidence" / "patch_diff_facts.json").read_text(encoding="utf-8"))
            source = json.loads((package / "materials" / "evidence" / "source.json").read_text(encoding="utf-8"))
            problem = json.loads((package / "materials" / "evidence" / "capture" / "capture-patch-problem-summary.json").read_text(encoding="utf-8"))
            risk = json.loads((package / "materials" / "evidence" / "capture" / "capture-risk-surface.json").read_text(encoding="utf-8"))

            self.assertEqual(check["status"], "PASS")
            self.assertEqual(manifest["schema"], "knowledge-incoming-package")
            self.assertEqual(manifest["schema_version"], "1")
            self.assertEqual(manifest["package_kind"], "framework_change")
            self.assertEqual(manifest["member_alias"], "admin_alias")
            self.assertEqual(manifest["package_status"], "validated")
            self.assertNotIn("maturity", manifest)
            self.assertFalse((package / "knowledge").exists())
            self.assertEqual(manifest["platform"], "rk")
            self.assertEqual(manifest["android_version"], "14")
            self.assertEqual(manifest["related_report_run_ids"], ["20260601-210000-daily"])
            self.assertEqual(manifest["implementation_origins"], ["manual"])
            self.assertEqual(manifest["capture_tools"], ["codex"])
            self.assertEqual(diff_facts["payload"]["implementation_origins"], ["manual"])
            self.assertEqual(diff_facts["payload"]["capture_tools"], ["codex"])
            self.assertEqual(diff_facts["payload"]["patches"][0]["implementation_origin"], "manual")
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
            self.assertIn("materials/evidence/source.json", evidence_files)
            self.assertIn("materials/evidence/project_inference.json", evidence_files)
            self.assertIn("materials/evidence/verification_result.json", evidence_files)
            self.assertFalse(any(str(path).startswith("knowledge/") for path in manifest["files"]["evidence"]))

    def test_patch_package_can_reference_original_needs_evidence_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = "20260612/lincong/20260612-172836-patch"
            reason = "补充项目（project）证据，原包 project=unknown。"
            package = intake.prepare_patch_package(
                dt.date(2026, 6, 12),
                self.config(root),
                run_id="20260612-190000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root, project="TVE1234A"))],
                project="TVE1234A",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
                supplement_for_package_key=target,
                supplement_reason=reason,
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            supplement = json.loads((package / "materials" / "evidence" / "evidence_supplement.json").read_text(encoding="utf-8"))
            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))

            self.assertEqual(check["status"], "PASS")
            self.assertEqual(manifest["package_kind"], "framework_change")
            self.assertEqual(manifest["supplement_for_package_key"], target)
            self.assertEqual(manifest["supplement_reason"], reason)
            self.assertIn("materials/evidence/evidence_supplement.json", manifest["files"]["evidence"])
            self.assertEqual(supplement["kind"], "evidence_supplement")
            self.assertEqual(supplement["payload"]["target_package_key"], target)
            self.assertEqual(supplement["payload"]["reason"], reason)
            self.assertEqual(supplement["payload"]["project"], "TVE1234A")

    def test_platform_token_parser_rejects_generic_android_prefix(self) -> None:
        self.assertEqual(
            intake.parse_platform_token(
                [
                    {
                        "path": "patches/android14-frameworks-base@cmss_logical_main_display.patch",
                    }
                ]
            ),
            ("unknown", "14"),
        )
        self.assertEqual(
            intake.parse_platform_token(
                [
                    {
                        "path": "patches/app15-manager@force-wifi-on.patch",
                    }
                ]
            ),
            ("unknown", "15"),
        )

    def test_platform_token_parser_accepts_only_supported_platforms(self) -> None:
        self.assertEqual(
            intake.parse_platform_token(
                [
                    {
                        "path": "patches/sprd14-frameworks-base@display-policy.patch",
                    },
                    {
                        "path": "patches/u14-settings@display-policy.patch",
                    },
                ]
            ),
            ("unisoc", "14"),
        )
        self.assertEqual(
            intake.parse_platform_token(
                [
                    {
                        "path": "patches/rk90-frameworks-base@display-policy.patch",
                    }
                ]
            ),
            ("rk", "9.0"),
        )

    def test_conflicting_project_clues_keep_project_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-130000-patch",
                patch_paths=[],
                patch_package_paths=[
                    str(
                        create_capture_package(
                            root,
                            project="TVE1234A",
                            source_root="/work/android/TVE9999U/frameworks/base",
                            git_branch="feature/TVE9999U-nav-policy",
                        )
                    )
                ],
                project="unknown",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            project_inference = json.loads((package / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "unknown")
            self.assertEqual(manifest["package_status"], "candidate")
            self.assertEqual(project_inference["payload"]["candidates"], ["TVE1234A", "TVE9999U"])
            self.assertTrue(any("多个项目型号" in item for item in project_inference["payload"]["limits"]))

    def test_framework_change_validation_rejects_fake_platform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root))],
                project="TVE1234A",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
            )
            manifest_path = package / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["platform"] = "android"
            write_json(manifest_path, manifest)
            variant_path = package / manifest["files"]["variant"]
            variant = json.loads(variant_path.read_text(encoding="utf-8"))
            variant["platform"] = "android"
            write_json(variant_path, variant)

            check = intake.validate_package(package)

            self.assertEqual(check["status"], "FAIL")
            self.assertTrue(any("platform 非法" in item for item in check["errors"]))

    def test_patch_package_carries_recent_member_search_usage_when_capture_lacks_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.config(root)
            write_member_search_usage(Path(config["out_dir"]), "2026-05-26", decision="adapt")
            patch_file = root / "rk14-frameworks-base@display-policy.patch"
            patch_file.write_text(
                "diff --git a/frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java b/frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java\n"
                "--- a/frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java\n"
                "+++ b/frameworks/base/services/core/java/com/android/server/wm/DisplayPolicy.java\n"
                "@@ -1 +1,2 @@\n"
                "+//gyf 20260526@ display policy\n",
                encoding="utf-8",
            )

            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                config,
                run_id="20260526-130000-patch",
                patch_paths=[str(patch_file)],
                patch_package_paths=[],
                project="TVE1234A",
                summary="显示策略适配",
                status="candidate",
                schema_version="1",
            )

            search_evidence = json.loads((package / "materials" / "evidence" / "search_before_change.json").read_text(encoding="utf-8"))
            payload = search_evidence["payload"]
            self.assertTrue(payload["searched"])
            self.assertEqual(payload["reuse_decision"], "adapt")
            self.assertEqual(payload["queries"], ["显示策略 split screen"])
            self.assertEqual(payload["targets"], ["case-display-policy"])

    def test_patch_package_uses_member_search_usage_when_capture_search_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.config(root)
            write_member_search_usage(Path(config["out_dir"]), "2026-05-26", decision="adapt")
            capture_package = create_capture_package(
                root,
                search_payload={
                    "result": "INFO",
                    "method": "knowledge_search",
                    "searched": False,
                    "queries": [],
                    "results": [],
                    "summary": "not provided by capture command",
                },
            )

            package = intake.prepare_patch_package(
                dt.date(2026, 5, 26),
                config,
                run_id="20260526-133000-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="TVE1234A",
                summary="显示策略适配",
                status="validated",
                schema_version="1",
            )

            search_evidence = json.loads((package / "materials" / "evidence" / "search_before_change.json").read_text(encoding="utf-8"))
            payload = search_evidence["payload"]
            self.assertTrue(payload["searched"])
            self.assertEqual(payload["reuse_decision"], "adapt")
            self.assertEqual(payload["queries"], ["显示策略 split screen"])
            self.assertEqual(payload["targets"], ["case-display-policy"])

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
            self.assertIn("materials/evidence/capture/capture-build-result.json", evidence_files)

            build_result = json.loads((package / "materials" / "evidence" / "capture" / "capture-build-result.json").read_text(encoding="utf-8"))
            self.assertEqual(build_result["kind"], "build_result")
            self.assertEqual(build_result["result"], "PASS")
            self.assertEqual(build_result["case_id"], manifest["case_id"])
            self.assertEqual(build_result["variant_id"], manifest["variant_id"])

    def test_capture_package_source_context_overrides_non_company_project_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_package = create_capture_package(
                root,
                project="mtk android16 Camera2",
                source_root="/home/test35/work/mtk/TVA10A2R/android16",
                git_branch="feature/TVA10A2R-camera2-reverseportrait",
            )
            package = intake.prepare_patch_package(
                dt.date(2026, 6, 4),
                self.config(root),
                run_id="20260604-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="mtk android16 Camera2",
                summary="Camera2 reversePortrait 方向补偿",
                status="candidate",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            variant = json.loads((package / "materials" / "variant.json").read_text(encoding="utf-8"))
            project_inference = json.loads((package / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "TVA10A2R")
            self.assertEqual(variant["project"], "TVA10A2R")
            self.assertEqual(project_inference["payload"]["project"], "TVA10A2R")
            self.assertTrue(project_inference["payload"]["company_rule_match"])

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
            variant = json.loads((package / "materials" / "variant.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["package_status"], "blocked")
            self.assertEqual(variant["package_status"], "blocked")

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
            self.assertEqual(manifest["package_status"], "candidate")

    def test_validated_capture_with_unknown_project_is_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = intake.prepare_patch_package(
                dt.date(2026, 6, 3),
                self.config(root),
                run_id="20260603-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root, project="mtk android16 Camera2"))],
                project="mtk android16 Camera2",
                summary="Camera2 reversePortrait 方向补偿",
                status="validated",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            variant = json.loads((package / "materials" / "variant.json").read_text(encoding="utf-8"))
            diff_facts = json.loads((package / "materials" / "evidence" / "patch_diff_facts.json").read_text(encoding="utf-8"))
            project_inference = json.loads((package / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "unknown")
            self.assertEqual(manifest["package_status"], "candidate")
            self.assertEqual(variant["package_status"], "candidate")
            self.assertFalse(diff_facts["payload"]["patches"][0]["reuse_hint"])
            self.assertIn("项目", diff_facts["payload"]["patches"][0]["note"])
            self.assertIn("命令参数 project 未匹配公司项目型号规范", " ".join(project_inference["payload"]["limits"]))

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
            verification = json.loads((package / "materials" / "evidence" / "verification_result.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["package_status"], "candidate")
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

    def test_case_solution_uses_patch_problem_summary_not_internal_wording(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch = root / "mtk16-camera2@reverseportrait.patch"
            patch.write_text(
                "diff --git a/host/AndroidManifest.xml b/host/AndroidManifest.xml\n"
                "--- a/host/AndroidManifest.xml\n"
                "+++ b/host/AndroidManifest.xml\n"
                "@@ -1 +1,2 @@\n"
                "+//guiliu 20260603@ reverse portrait camera\n",
                encoding="utf-8",
            )
            patch.with_suffix(".readme.md").write_text(valid_patch_readme(patch.stem), encoding="utf-8")

            package = intake.prepare_patch_package(
                dt.date(2026, 6, 3),
                self.config(root),
                run_id="20260603-120000-patch",
                patch_paths=[str(patch)],
                patch_package_paths=[],
                project="mtk android16 Camera2",
                summary="Camera2 reversePortrait 方向补偿",
                status="candidate",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            variant = json.loads((package / "materials" / "variant.json").read_text(encoding="utf-8"))
            case = json.loads((package / "materials" / "case.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["project"], "unknown")
            self.assertEqual(variant["project"], "unknown")
            self.assertNotIn("成员端 Codex 根据补丁 diff", case["solution_summary"])
            self.assertTrue(case["solution_summary"])

    def test_draft_patch_readme_marker_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch = root / "mtk15-frameworks-base@statusbar-policy.patch"
            patch.write_text(
                "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
                "--- a/frameworks/base/services/core/java/X.java\n"
                "+++ b/frameworks/base/services/core/java/X.java\n"
                "@@ -1 +1,2 @@\n"
                "+//gyf 20260601@ framework policy\n",
                encoding="utf-8",
            )
            patch.with_suffix(".readme.md").write_text("# 状态栏策略\n\n这是根据补丁 diff 自动生成的草稿说明。\n", encoding="utf-8")

            errors = intake.validate_patch_file(patch)

            self.assertTrue(any("草稿/模板说明" in item for item in errors))

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

    def test_feature_capture_package_uses_one_feature_readme_for_multiple_patches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = intake.prepare_patch_package(
                dt.date(2026, 6, 8),
                self.config(root),
                run_id="20260608-120000-feature",
                patch_paths=[],
                patch_package_paths=[str(create_feature_capture_package(root))],
                project="TVE1234A",
                summary="跨源码仓库调整显示策略和设置入口",
                status="validated",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))
            diff_facts = json.loads((package / "materials" / "evidence" / "patch_diff_facts.json").read_text(encoding="utf-8"))
            variant = json.loads((package / "materials" / "variant.json").read_text(encoding="utf-8"))

            self.assertEqual(check["status"], "PASS")
            self.assertEqual(manifest["files"]["readme"], "materials/readme.md")
            self.assertEqual(len(manifest["files"]["patches"]), 2)
            self.assertTrue((package / "materials" / "readme.md").is_file())
            self.assertFalse(list((package / "patches").glob("*.readme.md")))
            self.assertEqual(variant["repo_paths"], ["frameworks/base", "packages/apps/Settings"])
            self.assertEqual(variant["implementation_origins"], ["manual"])
            self.assertEqual(manifest["implementation_origins"], ["manual"])
            self.assertEqual(diff_facts["payload"]["patch_count"], 2)
            self.assertEqual(diff_facts["payload"]["implementation_origins"], ["manual"])
            self.assertEqual(
                {item["repo_path"] for item in diff_facts["payload"]["patches"]},
                {"frameworks/base", "packages/apps/Settings"},
            )
            self.assertEqual(
                {item["implementation_origin"] for item in diff_facts["payload"]["patches"]},
                {"manual"},
            )

    def test_template_patch_companion_readme_is_rejected_even_with_feature_readme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            standalone_patch = root / "rk14-frameworks-base@template-companion.patch"
            standalone_patch.write_text(
                "diff --git a/frameworks/base/services/core/java/Y.java b/frameworks/base/services/core/java/Y.java\n"
                "--- a/frameworks/base/services/core/java/Y.java\n"
                "+++ b/frameworks/base/services/core/java/Y.java\n"
                "@@ -1 +1,2 @@\n"
                "+//gyf 20260608@ template companion case\n",
                encoding="utf-8",
            )
            standalone_patch.with_suffix(".readme.md").write_text(
                intake.patch_readme_template(
                    intake.PatchInfo(path=standalone_patch, name=standalone_patch.name, project="TVE1234A"),
                    self.config(root),
                    status="validated",
                    reuse_hint=True,
                ),
                encoding="utf-8",
            )

            package = intake.prepare_patch_package(
                dt.date(2026, 6, 8),
                self.config(root),
                run_id="20260608-121000-template-companion",
                patch_paths=[str(standalone_patch)],
                patch_package_paths=[str(create_capture_package(root))],
                project="TVE1234A",
                summary="功能级说明合格但补丁说明未补齐",
                status="validated",
                schema_version="1",
            )

            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))
            project_inference = json.loads((package / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))

            self.assertEqual(check["status"], "FAIL")
            self.assertTrue(any("template-companion.readme.md" in item and "TODO" in item for item in check["errors"]))
            self.assertFalse(any("TODO" in item for item in project_inference["payload"]["raw_inputs"]))

    def test_project_inference_keeps_full_model_and_base_model(self) -> None:
        project, payload = intake.infer_project(
            "unknown",
            [{"project": "TVE1067M1_H031", "path": "patches/mtk16-settings@lockscreen.patch"}],
            [],
            "",
        )

        self.assertEqual(project, "TVE1067M1_H031")
        self.assertEqual(payload["base_model"], "TVE1067M1")
        self.assertEqual(payload["suffix"], "H031")
        self.assertTrue(payload["company_rule_match"])

    def test_daily_project_inference_collapses_same_base_model_candidates(self) -> None:
        project, payload = intake.infer_report_project(
            "daily",
            "今天处理 TVE1067M1 管理端应用下发，并修复 TVE1067M1_H031 分屏手势条黑屏。",
            {
                "TVE1067M1": [("管理端应用下发", "已完成")],
                "TVE1067M1_H031": [("分屏手势条黑屏", "已完成")],
            },
            [],
            [],
        )

        self.assertEqual(project, "TVE1067M1")
        self.assertEqual(payload["project"], "TVE1067M1")
        self.assertEqual(payload["base_model"], "TVE1067M1")
        self.assertIn("多个候选共享基础项目 TVE1067M1", " ".join(payload["limits"]))

    def test_patch_project_inference_uses_related_daily_report_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.config(root)
            daily = Path(config["out_dir"]) / "submitted" / "20260604" / "member01" / "20260604-210000-daily"
            (daily / "materials" / "evidence").mkdir(parents=True)
            write_json(
                daily / "manifest.json",
                {
                    "schema": "knowledge-incoming-package",
                    "schema_version": "1",
                    "package_kind": "daily_trace",
                    "member_alias": "member01",
                    "member_name": "Member One",
                    "date": "2026-06-04",
                    "run_id": "20260604-210000-daily",
                    "project": "TVE1086U",
                    "summary": "今天处理 TVE1086U 青鸾云 HDMI 副屏显示。",
                    "files": {"evidence": ["materials/evidence/project_inference.json"]},
                },
            )
            write_json(
                daily / "materials" / "evidence" / "project_inference.json",
                {
                    "kind": "project_inference",
                    "payload": {
                        "project": "TVE1086U",
                        "recognized": True,
                        "basis": ["日报上下文: 今天处理 TVE1086U 青鸾云 HDMI 副屏显示。"],
                    },
                },
            )
            capture_package = create_capture_package(
                root,
                project="unknown",
                source_root="/home/cong/work/mtk/b_mt8775_8792_tablet",
                git_branch="master",
                related_report_run_ids=["20260604-210000-daily"],
            )

            package = intake.prepare_patch_package(
                dt.date(2026, 6, 4),
                config,
                run_id="20260604-230000-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="unknown",
                summary="HDMI 副屏显示适配",
                status="candidate",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            variant = json.loads((package / "materials" / "variant.json").read_text(encoding="utf-8"))
            project_inference = json.loads((package / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "TVE1086U")
            self.assertEqual(variant["project"], "TVE1086U")
            self.assertEqual(project_inference["payload"]["project"], "TVE1086U")
            self.assertIn("关联日报", " ".join(project_inference["payload"]["basis"]))


if __name__ == "__main__":
    unittest.main()
