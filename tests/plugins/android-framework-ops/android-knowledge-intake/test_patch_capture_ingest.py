from __future__ import annotations

import datetime as dt
import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[4]
INTAKE_SKILL_DIR = REPO_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake"
SCRIPT = INTAKE_SKILL_DIR / "scripts" / "android_knowledge_intake.py"
SPEC = importlib.util.spec_from_file_location("android_knowledge_intake", SCRIPT)
assert SPEC and SPEC.loader
intake = importlib.util.module_from_spec(SPEC)
sys.modules["android_knowledge_intake"] = intake
SPEC.loader.exec_module(intake)

def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_patch_package(*args, **kwargs):
    """Delegate fixtures while making every direct patch an explicit manual import."""
    if kwargs.get("patch_paths") and "workflow_contract" not in kwargs:
        kwargs["workflow_contract"] = "manual_import"
    return intake.prepare_patch_package(*args, **kwargs)


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
    project: str = "TVE1067M",
    source_root: str | None = None,
    git_branch: str = "",
    git_remote: str = "",
    search_payload: dict | None = None,
    implementation_origin: str = "manual",
    workflow_contract: str = "current_codex_skill",
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
    write_json(
        package / "evidence" / "verification-result.json",
        {
            "contract_version": "akbs-verification-evidence/v2",
            "scope": "feature",
            "requirement_acceptance": "accepted",
            "result": "PASS",
            "method": "device",
            "build": ["framework-services build PASS"],
            "steps": ["navigation policy behavior matched expectation"],
            "summary": "device pass",
        },
    )
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
        "implementation_origin": implementation_origin,
        "workflow_contract": workflow_contract,
        "captured_by": "codex",
        "created_at": "2026-07-15T12:00:00+08:00",
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
                "implementation_origin": implementation_origin,
                "workflow_contract": workflow_contract,
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
    write_json(
        package / "evidence" / "verification-result.json",
        {
            "contract_version": "akbs-verification-evidence/v2",
            "scope": "feature",
            "requirement_acceptance": "accepted",
            "result": "PASS",
            "method": "device",
            "build": ["framework-services build PASS"],
            "steps": ["cross-repository display policy behavior matched expectation"],
            "summary": "device pass",
        },
    )
    write_json(
        package / "evidence" / "search-before-change.json",
        {
            "result": "INFO",
            "method": "knowledge_search",
            "searched": True,
            "queries": ["display policy"],
            "results": ["No reuse candidate found"],
            "decision": "not_found",
            "reuse_decision": "not_found",
        },
    )
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
        "project": "TVE1067M",
        "platform_token": "rk14",
        "platform": "rk",
        "android_version": "14",
        "summary": "跨源码仓库调整显示策略和设置入口",
        "status": "validated",
        "implementation_origin": "manual",
        "workflow_contract": "current_codex_skill",
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
                "project": "TVE1067M",
                "platform_token": "rk14",
                "platform": "rk",
                "android_version": "14",
                "implementation_origin": "manual",
                "workflow_contract": "current_codex_skill",
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
                "project": "TVE1067M",
                "platform_token": "rk14",
                "platform": "rk",
                "android_version": "14",
                "implementation_origin": "manual",
                "workflow_contract": "current_codex_skill",
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


def create_multi_feature_capture_package(root: Path, *, feature_limit: int | None = None) -> Path:
    package = create_capture_package(root, status="validated", project="TVE1086U")
    summary = (
        "TVE1086U 青鸾云 2026-06-12 今日补丁：HD 版本云电脑跳转逻辑、系统弹窗副屏显示、"
        "移除 F7/F8/F10/F12 功能按键、移除 Alt+Tab 最近任务组合键、"
        "云外设 App 录屏投屏申请自动允许、云外设 App USB 权限自动获取。"
    )
    readme = package / "README.md"
    readme.write_text(
        "# TVE1086U 青鸾云 2026-06-12 今日补丁\n\n"
        "## 功能描述\n\n"
        "面向 TVE1086U 青鸾云 sprd14 / Android 14 项目，整理 2026-06-12 今日完成的 6 个 Framework/SystemUI 相关补丁。"
        "补丁范围包括 HD 版本云电脑跳转逻辑、系统弹窗副屏显示、移除指定快捷键功能、"
        "移除 Alt+Tab 最近任务组合键、云外设 App 录屏/投屏授权自动允许，以及云外设 App USB 权限自动确认。\n\n"
        "## 修改点\n\n"
        "- 今日补丁按日期聚合了多个独立功能。\n\n"
        "## 日志控制\n\n"
        "无新增运行时日志。\n\n"
        "## SystemProperties\n\n"
        "无新增系统属性。\n\n"
        "## 字符串国际化\n\n"
        "无新增字符串资源。\n\n"
        "## 可回滚性\n\n"
        "应按功能拆分后分别回滚。\n",
        encoding="utf-8",
    )
    features = [
        ("rk14-frameworks-base@cloud-computer-intent.patch", "HD 版本云电脑跳转逻辑"),
        ("rk14-frameworks-base@secondary-display-dialog.patch", "系统弹窗副屏显示"),
        ("rk14-frameworks-base@remove-f7-f8-f10-f12.patch", "移除 F7/F8/F10/F12 功能按键"),
        ("rk14-frameworks-base@remove-alt-tab.patch", "移除 Alt+Tab 最近任务组合键"),
        ("rk14-systemui@allow-screen-recording.patch", "云外设 App 录屏投屏申请自动允许"),
        ("rk14-systemui@usb-default-permission.patch", "云外设 App USB 权限自动获取"),
    ]
    if feature_limit is not None:
        features = features[:feature_limit]
    patches = []
    for name, label in features:
        patch = package / "patches" / name
        patch.write_text(
            "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
            "--- a/frameworks/base/services/core/java/X.java\n"
            "+++ b/frameworks/base/services/core/java/X.java\n"
            "@@ -1 +1,2 @@\n"
            f"+//gyf 20260612@ {label}\n",
            encoding="utf-8",
        )
        patches.append(
            {
                "id": Path(name).stem,
                "path": f"patches/{name}",
                "repo_path": "frameworks/base",
                "source_root": "/work/android/frameworks/base",
                "status": "validated",
                "reuse_hint": True,
                "project": "TVE1086U",
                "platform_token": "rk14",
                "platform": "rk",
                "android_version": "14",
                "implementation_origin": "manual",
                "captured_by": "codex",
                "facts": {"modified_files": ["frameworks/base/services/core/java/X.java"], "modules": ["frameworks-base"]},
            }
        )
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["summary"] = summary
    manifest["project"] = "TVE1086U"
    manifest["patches"] = patches
    write_json(manifest_path, manifest)
    return package


def write_member_search_usage(
    out_dir: Path,
    date: str,
    decision: str = "adapt",
    query: str = "显示策略 split screen",
    targets: list[str] | None = None,
    match_points: list[str] | None = None,
    mismatch_points: list[str] | None = None,
    reason: str = "复用思路但需要适配当前项目",
    results: list[dict[str, str]] | None = None,
) -> Path:
    targets = targets or ["case-display-policy"]
    match_points = match_points or ["同类显示策略"]
    mismatch_points = mismatch_points or ["项目源码路径不同"]
    results = results or [{"kind": "case", "id": "case-display-policy", "title": "显示策略"}]
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
                "query": query,
                "type": "all",
                "searched": True,
                "decision": decision,
                "reuse_decision": decision,
                "targets": targets,
                "match_points": match_points,
                "mismatch_points": mismatch_points,
                "reason": reason,
                "outcome": "not_started",
                "result_count": 1,
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


class PatchCaptureIngestTests(unittest.TestCase):
    def test_rejects_out_dir_under_plugin_skill_source(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            intake.require_safe_artifact_path(INTAKE_SKILL_DIR / "pending", purpose="out_dir")

        self.assertIn("不能写入插件 skill 源码目录", str(ctx.exception))

    def config(self, root: Path) -> dict[str, str]:
        return {
            "member_alias": "admin_alias",
            "member_name": "管理员姓名",
            "out_dir": str(root / "out"),
            "repo_url": "test35:/home/test35/work/akbs/remote.git",
            "max_attachment_mb": "5",
            "timezone": "Asia/Shanghai",
            "synthetic_data": "false",
        }

    def test_patch_builder_never_discovers_implicit_cwd_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mounted = root / "mounted-android"
            mounted.mkdir()
            (mounted / "rk14-frameworks-base@must-not-discover.patch").write_text(
                "mounted source patch\n", encoding="utf-8"
            )

            with patch.object(Path, "cwd", return_value=mounted), self.assertRaises(SystemExit) as ctx:
                intake.prepare_patch_package(
                    dt.date(2026, 8, 26),
                    self.config(root),
                    run_id="20260826-120000-patch",
                    patch_paths=[],
                    patch_package_paths=[],
                    project="TVE1088U",
                    status="candidate",
                    schema_version="1",
                )

            self.assertIn("不会从 cwd 自动发现补丁", str(ctx.exception))

    def test_direct_patch_requires_explicit_manual_or_historical_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch_path = root / "rk14-frameworks-base@manual.patch"
            patch_path.write_text("manual patch\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as ctx:
                intake.prepare_patch_package(
                    dt.date(2026, 8, 26),
                    self.config(root),
                    run_id="20260826-120100-patch",
                    patch_paths=[str(patch_path)],
                    patch_package_paths=[],
                    project="TVE1088U",
                    status="candidate",
                    schema_version="1",
                )

            self.assertIn("manual_import 或 historical_import", str(ctx.exception))

    def test_direct_patch_marker_gate_runs_before_creating_an_incoming_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch_path = root / "rk14-frameworks-base@manual.patch"
            patch_path.write_text(
                "diff --git a/frameworks/base/X.java b/frameworks/base/X.java\n"
                "--- a/frameworks/base/X.java\n"
                "+++ b/frameworks/base/X.java\n"
                "@@ -1 +1 @@\n"
                "+manualChange();\n",
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as ctx:
                prepare_patch_package(
                    dt.date(2026, 8, 26),
                    self.config(root),
                    run_id="20260826-120200-patch",
                    patch_paths=[str(patch_path)],
                    patch_package_paths=[],
                    project="TVE1088U",
                    status="draft",
                    schema_version="1",
                )

            self.assertIn("patch has no author/date marker", str(ctx.exception))
            self.assertFalse(Path(self.config(root)["out_dir"]).exists())

    def test_direct_historical_patch_keeps_a_valid_legacy_author_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patch_path = root / "rk14-frameworks-base@historical.patch"
            patch_path.write_text(
                "diff --git a/frameworks/base/X.java b/frameworks/base/X.java\n"
                "--- a/frameworks/base/X.java\n"
                "+++ b/frameworks/base/X.java\n"
                "@@ -1 +1 @@\n"
                "+//legacy_author 20251016@ historical change\n",
                encoding="utf-8",
            )

            errors = intake.validate_patch_file(patch_path)
            self.assertFalse(any("作者日期标记无效" in item for item in errors))

    def test_non_framework_capture_is_rejected_by_framework_incoming_v1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = create_capture_package(root, status="candidate")
            manifest_path = capture / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["package_type"] = "android_feature_patch"
            manifest["change_domain"] = "app"
            write_json(manifest_path, manifest)

            with self.assertRaises(SystemExit) as ctx:
                prepare_patch_package(
                    dt.date(2026, 8, 31),
                    self.config(root),
                    run_id="20260831-120000-app-capture",
                    patch_paths=[],
                    patch_package_paths=[str(capture)],
                    project="TVE1067M",
                    summary="App 领域本地材料",
                    status="candidate",
                    schema_version="1",
                )

            self.assertIn("incoming v1 只接受 change_domain=framework", str(ctx.exception))
            self.assertIn("app capture 只能保留为本地工程材料", str(ctx.exception))

    def test_patch_facts_extract_added_xml_string_resource_names(self) -> None:
        facts = intake.patch_facts_from_text(
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

    def test_patch_facts_ignore_context_anchors_for_scope_evidence(self) -> None:
        facts = intake.patch_facts_from_text(
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

    def test_capture_package_generates_framework_change_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root, related_report_run_ids=["20260601-210000-daily"]))],
                project="TVE1067M",
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
            patch_view = json.loads((package / "materials" / "display" / "patch_view.json").read_text(encoding="utf-8"))
            ai_facts = json.loads((package / "materials" / "evidence" / "patch_ai_facts.json").read_text(encoding="utf-8"))
            verification = json.loads(
                (package / "materials" / "evidence" / "verification_result.json").read_text(encoding="utf-8")
            )

            self.assertEqual(check["status"], "PASS", check["errors"])
            self.assertEqual(manifest["schema"], "knowledge-incoming-package")
            self.assertEqual(manifest["schema_version"], "1")
            self.assertEqual(manifest["package_kind"], "framework_change")
            self.assertEqual(manifest["member_alias"], "admin_alias")
            self.assertEqual(manifest["package_status"], "validated")
            self.assertEqual(verification["payload"]["scope"], "feature")
            self.assertEqual(verification["payload"]["requirement_acceptance"], "accepted")
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
            self.assertIn("materials/evidence/patch_ai_facts.json", evidence_files)
            self.assertEqual(manifest["files"]["display"], ["materials/display/patch_view.json"])
            self.assertEqual(patch_view["kind"], "patch_view")
            self.assertEqual(patch_view["payload"]["package_label"], "补丁包")
            self.assertEqual(patch_view["payload"]["display_title"], "Allow nav policy toggle")
            self.assertIn("ui_card", patch_view["payload"])
            self.assertGreaterEqual(len(patch_view["payload"]["detail_sections"]), 5)
            self.assertNotIn("case-", patch_view["payload"]["display_title"])
            self.assertEqual(ai_facts["kind"], "patch_ai_facts")
            self.assertEqual(ai_facts["case_id"], manifest["case_id"])
            self.assertEqual(ai_facts["variant_id"], manifest["variant_id"])
            self.assertTrue(ai_facts["payload"]["module"])
            self.assertTrue(ai_facts["payload"]["feature_domain"])
            self.assertTrue(ai_facts["payload"]["patch_behavior_goal"])
            self.assertTrue(ai_facts["payload"]["code_anchors"]["files"])
            self.assertEqual(ai_facts["payload"]["merge_gate_inputs"]["project"], "TVE1067M")
            self.assertFalse(any(str(path).startswith("knowledge/") for path in manifest["files"]["evidence"]))

    def test_delivery_only_and_legacy_unscoped_evidence_do_not_upgrade_to_validated(self) -> None:
        variants = {
            "delivery-only": {
                "contract_version": "akbs-verification-evidence/v2",
                "scope": "build_delivery",
                "requirement_acceptance": "unverified",
                "result": "PASS",
                "method": "device",
                "summary": "artifact delivery passed",
            },
            "legacy-unscoped": {
                "result": "PASS",
                "method": "device",
                "summary": "legacy device result without an acceptance scope",
            },
            "incomplete-feature-acceptance": {
                "contract_version": "akbs-verification-evidence/v2",
                "scope": "feature",
                "requirement_acceptance": "accepted",
                "result": "PASS",
                "method": "device",
                "summary": "acceptance marker without build or behavior steps",
            },
        }
        for label, verification_payload in variants.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                capture = create_capture_package(root)
                write_json(capture / "evidence" / "verification-result.json", verification_payload)

                package = prepare_patch_package(
                    dt.date(2026, 5, 26),
                    self.config(root),
                    run_id="20260526-120500-patch",
                    patch_paths=[],
                    patch_package_paths=[str(capture)],
                    project="TVE1067M",
                    summary="Allow nav policy toggle",
                    status="validated",
                    schema_version="1",
                )

                manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
                stored = json.loads(
                    (package / "materials" / "evidence" / "verification_result.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["package_status"], "candidate")
                self.assertEqual(stored["payload"], verification_payload)

    def test_patch_ai_facts_treat_adapt_as_reference_not_merge_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = create_capture_package(
                root,
                search_payload={
                    "result": "INFO",
                    "method": "knowledge_search",
                    "searched": True,
                    "queries": ["nav policy"],
                    "results": ["case-nav-policy can provide implementation reference"],
                    "decision": "adapt",
                    "reuse_decision": "adapt",
                    "targets": ["case-nav-policy"],
                    "summary": "参考已有导航策略案例，但当前项目需要适配。",
                },
            )

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-121000-patch",
                patch_paths=[],
                patch_package_paths=[str(capture)],
                project="TVE1067M",
                summary="导航策略适配",
                status="candidate",
                schema_version="1",
            )

            ai_facts = json.loads((package / "materials" / "evidence" / "patch_ai_facts.json").read_text(encoding="utf-8"))

            self.assertEqual(ai_facts["payload"]["search_match_class"]["decision"], "adapt")
            self.assertEqual(ai_facts["payload"]["search_match_class"]["merge_hint"], "reference_only")
            self.assertIn("不能直接触发合并", ai_facts["payload"]["search_match_class"]["explanation"])

    def test_framework_change_validation_requires_patch_view_and_ai_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root))],
                project="TVE1067M",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
            )
            manifest_path = package / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"].pop("display", None)
            manifest["files"]["evidence"] = [
                rel for rel in manifest["files"]["evidence"] if rel != "materials/evidence/patch_ai_facts.json"
            ]
            write_json(manifest_path, manifest)

            check = intake.validate_package(package)

            self.assertEqual(check["status"], "FAIL")
            self.assertTrue(any("files.display" in item for item in check["errors"]))
            self.assertTrue(any("patch_ai_facts" in item for item in check["errors"]))

    def test_multi_feature_daily_bundle_fails_local_check_with_function_split_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = (
                "TVE1086U 青鸾云 2026-06-12 今日补丁：HD 版本云电脑跳转逻辑、系统弹窗副屏显示、"
                "移除 F7/F8/F10/F12 功能按键、移除 Alt+Tab 最近任务组合键、"
                "云外设 App 录屏投屏申请自动允许、云外设 App USB 权限自动获取。"
            )
            with self.assertRaises(SystemExit) as raised:
                prepare_patch_package(
                    dt.date(2026, 6, 12),
                    self.config(root),
                    run_id="20260612-233425-patch",
                    patch_paths=[],
                    patch_package_paths=[str(create_multi_feature_capture_package(root))],
                    project="TVE1086U",
                    summary=summary,
                    status="validated",
                    schema_version="1",
                )

            message = str(raised.exception)
            self.assertIn("聚合包", message)
            self.assertIn("按功能拆分", message)
            self.assertIn("新的补丁包", message)
            self.assertFalse((root / "out" / "pending" / "20260612" / "admin_alias" / "20260612-233425-patch").exists())

    def test_date_bundled_two_patch_package_fails_local_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = "TVE1086U 青鸾云 2026-06-12 今日补丁：HD 版本云电脑跳转逻辑、系统弹窗副屏显示。"
            with self.assertRaises(SystemExit) as raised:
                prepare_patch_package(
                    dt.date(2026, 6, 12),
                    self.config(root),
                    run_id="20260612-233426-patch",
                    patch_paths=[],
                    patch_package_paths=[str(create_multi_feature_capture_package(root, feature_limit=2))],
                    project="TVE1086U",
                    summary=summary,
                    status="candidate",
                    schema_version="1",
                )

            message = str(raised.exception)
            self.assertIn("聚合包", message)
            self.assertIn("按功能拆分", message)
            self.assertFalse((root / "out" / "pending" / "20260612" / "admin_alias" / "20260612-233426-patch").exists())

    def test_scope_polluted_patch_package_fails_local_check_with_patch_asset_correction_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = create_capture_package(root, project="TVE8801M")
            summary = "新增电池页性能模式三档，联动刷新率与 PowerHAL LOW/SUSTAINED 模式，并补齐中文/韩文节能文案"
            (capture / "README.md").write_text(
                "# add-device-performance-mode\n\n"
                "## 功能描述\n\n"
                f"{summary}\n\n"
                "## 修改点\n\n"
                "- 修改 MtkSettings 字符串和性能模式入口。\n\n"
                "## 日志控制\n\n"
                "无新增运行时日志。\n\n"
                "## SystemProperties\n\n"
                "无新增系统属性。\n\n"
                "## 字符串国际化\n\n"
                "新增性能模式中英韩文案。\n\n"
                "## 可回滚性\n\n"
                "回滚该 patch 后恢复原性能模式资源。\n",
                encoding="utf-8",
            )
            patch_path = capture / "patches" / "rk14-frameworks-base@nav-policy-toggle.patch"
            patch_path.write_text(
                "diff --git a/res/values/strings.xml b/res/values/strings.xml\n"
                "--- a/res/values/strings.xml\n"
                "+++ b/res/values/strings.xml\n"
                "@@ -1,3 +1,20 @@\n"
                "+//gyf 20260623@ add performance mode resources\n"
                "+<string name=\"performance_mode_title\">Performance mode</string>\n"
                "+<string name=\"performance_mode_power_save\">Eco mode</string>\n"
                "+<string name=\"proxy_tip\">HTTP proxy used by the browser</string>\n"
                "+<string name=\"select_ethernet_device\">Select Ethernet device</string>\n"
                "+<string name=\"three_finger_swipe_down_action_screenshot\">Screenshot</string>\n"
                "+<string name=\"ram_extender_title\">RAM Extender</string>\n"
                "+<string name=\"zone_auto_summaryOn\">Use network-provided time zone</string>\n",
                encoding="utf-8",
            )

            package = prepare_patch_package(
                dt.date(2026, 6, 23),
                self.config(root),
                run_id="20260623-195544-patch",
                patch_paths=[],
                patch_package_paths=[str(capture)],
                project="TVE8801M",
                summary=summary,
                status="validated",
                schema_version="1",
            )

            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))

            self.assertEqual(check["status"], "FAIL")
            errors = "\n".join(check["errors"])
            self.assertIn("重新采集同一功能补丁包", errors)
            self.assertIn("proxy_tip", errors)
            self.assertNotIn("按日期聚合", errors)

    def test_multiple_raw_patch_files_fail_before_package_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patches: list[str] = []
            for name in [
                "rk14-frameworks-base@cloud-computer-intent.patch",
                "rk14-systemui@usb-default-permission.patch",
            ]:
                patch = root / name
                patch.write_text(
                    "diff --git a/frameworks/base/services/core/java/X.java b/frameworks/base/services/core/java/X.java\n"
                    "--- a/frameworks/base/services/core/java/X.java\n"
                    "+++ b/frameworks/base/services/core/java/X.java\n"
                    "@@ -1 +1,2 @@\n"
                    "+//gyf 20260612@ raw patch should be captured by skill first\n",
                    encoding="utf-8",
                )
                patches.append(str(patch))

            with self.assertRaises(SystemExit) as context:
                prepare_patch_package(
                    dt.date(2026, 6, 12),
                    self.config(root),
                    run_id="20260612-235900-raw-multi",
                    patch_paths=patches,
                    patch_package_paths=[],
                    project="TVE1086U",
                    summary="两个原始 patch 直接上传",
                    status="candidate",
                    schema_version="1",
                )

            self.assertIn("直接 --patch 只允许单个独立补丁", str(context.exception))
            self.assertFalse((root / "pending" / "20260612" / "member1" / "20260612-235900-raw-multi").exists())

    def test_submit_blocks_ordinary_candidate_patch_package_before_server_upload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = prepare_patch_package(
                dt.date(2026, 6, 12),
                self.config(root),
                run_id="20260612-190003-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root, status="candidate"))],
                project="TVE1067M",
                summary="Allow nav policy toggle",
                status="candidate",
                schema_version="1",
            )

            with self.assertRaises(SystemExit) as raised:
                intake.submit_package(package, self.config(root))

            message = str(raised.exception)
            self.assertIn("普通补丁包", message)
            self.assertIn("已验证（validated）", message)

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

    def test_platform_metadata_uses_unique_verification_token_when_patch_name_lacks_platform(self) -> None:
        self.assertEqual(
            intake.infer_platform_metadata(
                [{"path": "patches/A15A16-manager@app_distribution_fix.patch"}],
                [{"payload": {"details": ["project model: TVE1067M1_H031", "platform: mtk15"]}}],
            ),
            ("mtk", "15"),
        )

    def test_conflicting_project_clues_keep_project_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-130000-patch",
                patch_paths=[],
                patch_package_paths=[
                    str(
                        create_capture_package(
                            root,
                            project="TVE1067M",
                            source_root="/work/android/TVE1086U/frameworks/base",
                            git_branch="feature/TVE1086U-nav-policy",
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
            self.assertEqual(project_inference["payload"]["candidates"], ["TVE1067M", "TVE1086U"])
            self.assertTrue(any("多个项目型号" in item for item in project_inference["payload"]["limits"]))

    def test_framework_change_validation_rejects_fake_platform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root))],
                project="TVE1067M",
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

    def test_framework_change_validation_rejects_garbled_question_mark_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root))],
                project="TVE1067M",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
            )
            manifest_path = package / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["summary"] = "?????????????"
            write_json(manifest_path, manifest)
            case_path = package / manifest["files"]["case"]
            case = json.loads(case_path.read_text(encoding="utf-8"))
            case["title"] = "?????????????"
            write_json(case_path, case)

            check = intake.validate_package(package)

            self.assertEqual(check["status"], "FAIL")
            self.assertTrue(any("manifest.summary" in item and "问号乱码" in item for item in check["errors"]))
            self.assertTrue(any("case.title" in item and "问号乱码" in item for item in check["errors"]))

    def test_framework_change_validation_rejects_uncontrolled_app_patch_asset_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root))],
                project="TVE1067M",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
            )
            manifest_path = package / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            old_rel = manifest["files"]["patches"][0]
            new_rel = "patches/app15-frameworks-base@nav-policy-toggle.patch"
            (package / old_rel).rename(package / new_rel)
            manifest["files"]["patches"][0] = new_rel
            write_json(manifest_path, manifest)
            facts_path = package / "materials" / "evidence" / "patch_diff_facts.json"
            facts = json.loads(facts_path.read_text(encoding="utf-8"))
            facts["payload"]["patches"][0]["path"] = new_rel
            write_json(facts_path, facts)

            check = intake.validate_package(package)

            self.assertEqual(check["status"], "FAIL")
            self.assertTrue(any("app15" in item and "补丁资产" in item for item in check["errors"]))

    def test_patch_search_payload_selection_stays_in_evidence_helper(self) -> None:
        capture_payload = {
            "searched": True,
            "queries": ["capture query"],
            "reuse_decision": "reuse",
        }
        member_payload = {
            "searched": True,
            "queries": ["member query"],
            "reuse_decision": "adapt",
        }

        self.assertIs(
            intake.select_search_before_change_payload(
                capture_search_payload=capture_payload,
                member_search_payload=member_payload,
                capture_has_member_decision=True,
            ),
            capture_payload,
        )
        self.assertIs(
            intake.select_search_before_change_payload(
                capture_search_payload={"searched": True, "reuse_decision": "unknown"},
                member_search_payload=member_payload,
                capture_has_member_decision=False,
            ),
            member_payload,
        )
        self.assertEqual(
            intake.select_search_before_change_payload(
                capture_search_payload={},
                member_search_payload={},
                capture_has_member_decision=False,
            )["searched"],
            False,
        )
        self.assertEqual(
            intake.verification_payload_or_missing({"result": "PASS", "method": "device"})["result"],
            "PASS",
        )
        self.assertEqual(intake.verification_payload_or_missing({})["result"], "MISSING")

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

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                config,
                run_id="20260526-130000-patch",
                patch_paths=[str(patch_file)],
                patch_package_paths=[],
                project="TVE1067M",
                summary="显示策略适配",
                status="candidate",
                schema_version="1",
            )

            search_evidence = json.loads((package / "materials" / "evidence" / "search_before_change.json").read_text(encoding="utf-8"))
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            payload = search_evidence["payload"]
            self.assertEqual(manifest["workflow_contract"], "manual_import")
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
                implementation_origin="codex",
            )

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                config,
                run_id="20260526-133000-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="TVE1067M",
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

    def test_patch_package_prefers_member_search_usage_when_capture_decision_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.config(root)
            write_member_search_usage(Path(config["out_dir"]), "2026-05-26", decision="adapt")
            capture_package = create_capture_package(
                root,
                search_payload={
                    "result": "INFO",
                    "method": "knowledge_search",
                    "searched": True,
                    "queries": ["navigation policy toggle"],
                    "results": ["case-nav-policy matched modified files"],
                    "decision": "unknown",
                    "reuse_decision": "unknown",
                    "summary": "capture command did not close usage decision",
                },
            )

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                config,
                run_id="20260526-134000-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="TVE1067M",
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

    def test_validated_patch_package_rejects_unknown_search_decision_for_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_package = create_capture_package(
                root,
                search_payload={
                    "result": "INFO",
                    "method": "knowledge_search",
                    "searched": True,
                    "queries": ["navigation policy toggle"],
                    "results": ["case-nav-policy matched modified files"],
                    "decision": "unknown",
                    "reuse_decision": "unknown",
                    "summary": "capture command did not close usage decision",
                },
            )

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-134500-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="TVE1067M",
                summary="显示策略适配",
                status="validated",
                schema_version="1",
            )

            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))
            self.assertEqual(check["status"], "FAIL")
            errors = "\n".join(check["errors"])
            self.assertIn("搜索使用决策", errors)
            self.assertIn("reuse/adapt/reference_only/not_applicable/not_found", errors)

    def test_codex_validated_patch_package_rejects_missing_pre_change_search_without_faking_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
                implementation_origin="codex",
            )

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-134800-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="TVE1067M",
                summary="显示策略适配",
                status="validated",
                schema_version="1",
            )

            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))
            search_evidence = json.loads((package / "materials" / "evidence" / "search_before_change.json").read_text(encoding="utf-8"))
            self.assertEqual(check["status"], "FAIL")
            self.assertFalse(search_evidence["payload"]["searched"])
            errors = "\n".join(check["errors"])
            self.assertIn("开发前知识搜索", errors)
            self.assertIn("不能事后补造", errors)
            self.assertIn("保持真实工作流和实施来源", errors)
            self.assertNotIn("改用手动实现", errors)

    def test_workflow_contract_not_implementation_origin_controls_search_gate(self) -> None:
        self.assertTrue(
            intake.workflow_contract_requires_pre_change_search(
                "current_codex_skill"
            )
        )
        self.assertFalse(
            intake.workflow_contract_requires_pre_change_search("manual_import")
        )
        self.assertFalse(
            intake.workflow_contract_requires_pre_change_search("historical_import")
        )

    def test_mixed_validated_patch_package_rejects_missing_pre_change_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
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
                implementation_origin="mixed",
            )

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-134850-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="TVE1067M",
                summary="显示策略适配",
                status="validated",
                schema_version="1",
            )

            check = json.loads(
                (package / "local-check.json").read_text(encoding="utf-8")
            )
            self.assertEqual(check["status"], "FAIL")
            errors = "\n".join(check["errors"])
            self.assertIn("current_codex_skill", errors)
            self.assertIn("保持真实工作流和实施来源", errors)
            self.assertNotIn("改用手动实现", errors)

    def test_manual_validated_patch_package_allows_missing_pre_change_search_without_faking_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_package = create_capture_package(
                root,
                search_payload={
                    "result": "INFO",
                    "method": "knowledge_search",
                    "searched": False,
                    "queries": [],
                    "results": [],
                    "summary": "手动实现（manual implementation）开发前未搜索，不能事后补造。",
                },
                implementation_origin="manual",
                workflow_contract="manual_import",
            )

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-134900-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="TVE1067M",
                summary="显示策略适配",
                status="validated",
                schema_version="1",
            )

            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))
            search_evidence = json.loads((package / "materials" / "evidence" / "search_before_change.json").read_text(encoding="utf-8"))
            source_evidence = json.loads((package / "materials" / "evidence" / "source.json").read_text(encoding="utf-8"))

            self.assertEqual(check["status"], "PASS")
            self.assertFalse(search_evidence["payload"]["searched"])
            self.assertIn("手动实现", search_evidence["payload"]["summary"])
            self.assertEqual(source_evidence["payload"]["implementation_origin"], "manual")
            self.assertEqual(source_evidence["payload"]["implementation_origins"], ["manual"])
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["workflow_contract"], "manual_import")
            warnings = "\n".join(check["warnings"])
            self.assertIn("沉淀前重叠检索", warnings)

    def test_historical_import_can_record_codex_as_origin_without_faking_current_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_package = create_capture_package(
                root,
                search_payload={
                    "result": "INFO",
                    "method": "knowledge_search",
                    "searched": False,
                    "queries": [],
                    "results": [],
                    "summary": "历史记录没有开发前检索回执，不能事后补造。",
                },
                implementation_origin="codex",
                workflow_contract="historical_import",
            )

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-135000-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="TVE1067M",
                summary="显示策略历史归档",
                status="validated",
                schema_version="1",
            )

            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(check["status"], "PASS")
            self.assertEqual(manifest["implementation_origins"], ["codex"])
            self.assertEqual(manifest["workflow_contract"], "historical_import")

    def test_capture_workflow_cannot_be_overridden_by_the_import_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_package = create_capture_package(
                root,
                implementation_origin="manual",
                workflow_contract="manual_import",
            )

            with self.assertRaises(SystemExit) as raised:
                prepare_patch_package(
                    dt.date(2026, 5, 26),
                    self.config(root),
                    run_id="20260526-135100-patch",
                    patch_package_paths=[str(capture_package)],
                    project="TVE1067M",
                    summary="显示策略手工导入",
                    status="validated",
                    schema_version="1",
                    workflow_contract="current_codex_skill",
                )

            self.assertIn("不能通过导入参数改写", str(raised.exception))

    def test_legacy_capture_requires_an_explicit_import_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture_package = create_capture_package(
                root,
                implementation_origin="codex",
                workflow_contract="",
            )

            with self.assertRaises(SystemExit) as missing:
                prepare_patch_package(
                    dt.date(2026, 5, 26),
                    self.config(root),
                    run_id="20260526-135200-patch",
                    patch_package_paths=[str(capture_package)],
                    project="TVE1067M",
                    summary="显示策略历史导入",
                    status="validated",
                    schema_version="1",
                )
            self.assertIn("必须显式使用 --workflow-contract", str(missing.exception))

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-135201-patch",
                patch_package_paths=[str(capture_package)],
                project="TVE1067M",
                summary="显示策略历史导入",
                status="validated",
                schema_version="1",
                workflow_contract="historical_import",
            )
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["workflow_contract"], "historical_import")

    def test_patch_package_does_not_attach_unrelated_same_day_search_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.config(root)
            write_member_search_usage(
                Path(config["out_dir"]),
                "2026-06-18",
                decision="adapt",
                query="DeviceCtrlService 后台网络权限",
                targets=["case-device-ctrl-service-permission"],
                match_points=["DeviceCtrlService 后台控制链路"],
                mismatch_points=["权限配置不同"],
                reason="同日搜索过 DeviceCtrlService 权限问题",
                results=[{"kind": "case", "id": "case-device-ctrl-service-permission", "title": "DeviceCtrlService 权限配置"}],
            )
            capture_package = create_capture_package(
                root,
                search_payload={
                    "result": "INFO",
                    "method": "knowledge_search",
                    "searched": False,
                    "queries": [],
                    "results": [],
                    "summary": "capture package did not provide pre-change search",
                },
            )

            package = prepare_patch_package(
                dt.date(2026, 6, 18),
                config,
                run_id="20260618-204354-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="TVE1067M",
                summary="关闭低版本 APK 警告和 APK 不适配警告",
                status="candidate",
                schema_version="1",
            )

            search_evidence = json.loads((package / "materials" / "evidence" / "search_before_change.json").read_text(encoding="utf-8"))
            payload = search_evidence["payload"]
            self.assertFalse(payload["searched"])
            self.assertNotIn("DeviceCtrlService 后台网络权限", payload.get("queries", []))

    def test_capture_package_preserves_optional_build_result_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root, include_build_result=True))],
                project="TVE1067M",
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
            package = prepare_patch_package(
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

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-130000-patch",
                patch_paths=[str(patch)],
                patch_package_paths=[],
                project="TVE1067M",
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

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-140000-patch",
                patch_paths=[str(patch)],
                patch_package_paths=[],
                project="TVE1067M",
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
                    intake.PatchInfo(path=patch, name=patch.name, project="TVE1067M"),
                    self.config(root),
                ),
                encoding="utf-8",
            )

            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-150000-patch",
                patch_paths=[str(patch)],
                patch_package_paths=[],
                project="TVE1067M",
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
            package = prepare_patch_package(
                dt.date(2026, 5, 26),
                self.config(root),
                run_id="20260526-120000-patch",
                patch_paths=[],
                patch_package_paths=[str(create_capture_package(root, status="candidate"))],
                project="TVE1067M",
                summary="Allow nav policy toggle",
                status="validated",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["package_status"], "candidate")

    def test_validated_capture_with_unknown_project_is_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = prepare_patch_package(
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

            package = prepare_patch_package(
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

            first = prepare_patch_package(
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
            second = prepare_patch_package(
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

            package = prepare_patch_package(
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

    def test_eink_package_rejects_camera_template_leak_in_case_and_problem_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = create_capture_package(root, project="TVE1067M")
            (capture / "README.md").write_text(
                valid_patch_readme("E-Ink display mode"),
                encoding="utf-8",
            )
            patch_path = capture / "patches" / "rk14-frameworks-base@nav-policy-toggle.patch"
            patch_path.write_text(
                "diff --git a/frameworks/base/core/res/res/values/config.xml b/frameworks/base/core/res/res/values/config.xml\n"
                "--- a/frameworks/base/core/res/res/values/config.xml\n"
                "+++ b/frameworks/base/core/res/res/values/config.xml\n"
                "@@ -1 +1,2 @@\n"
                "+<!-- lincong 20260627@ E-Ink display mode -->\n",
                encoding="utf-8",
            )
            problem_path = capture / "evidence" / "patch-problem-summary.json"
            write_json(
                problem_path,
                {
                    "kind": "patch_problem_summary",
                    "confidence": "medium",
                    "problem_summary": "相机预览、扫码、拍照或相机权限行为可能不符合产品要求。",
                    "solution_summary": "调整 CameraService、Camera2 或相机 HAL 相关路径，并验证目标相机场景。",
                    "basis": ["patch modifies frameworks/base/core/res/res/values/config.xml"],
                    "limits": ["verification is separate"],
                },
            )

            package = prepare_patch_package(
                dt.date(2026, 6, 27),
                self.config(root),
                run_id="20260627-020909-patch",
                patch_paths=[],
                patch_package_paths=[str(capture)],
                project="TVE1067M",
                summary="E-Ink 显示模式补丁资产修正",
                status="validated",
                schema_version="1",
            )

            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))

            self.assertEqual(check["status"], "FAIL")
            errors = "\n".join(check["errors"])
            self.assertIn("模板文本泄漏", errors)
            self.assertIn("相机", errors)

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

    def test_statusbar_paths_do_not_trigger_usb_semantics(self) -> None:
        files = [
            "src/com/android/systemui/statusbar/notification/stack/MediaContainerView.kt",
            "src/com/android/systemui/statusbar/notification/stack/NotificationStackScrollLayoutController.java",
            "src/com/android/systemui/keyguard/ui/view/layout/sections/DefaultMediaSection.kt",
        ]
        modules = intake.patch_modules_from_files(files)
        problem, risk = intake.patch_problem_and_risk_payloads(
            "patch-systemui-media",
            "patches/mtk16-systemui@Display_media_controls_in_portrait_mode.patch",
            "SystemUI 锁屏媒体控件支持竖屏显示",
            {"modified_files": files, "modules": modules, "symbols": []},
        )

        self.assertIn("SystemUI", modules)
        self.assertNotIn("USB", modules)
        self.assertNotIn("USB", problem["problem_summary"])
        self.assertNotIn("USB", problem["solution_summary"])
        self.assertNotIn("USB/设备权限", problem["keywords"])
        self.assertNotIn("USB/设备权限", risk["risk_areas"])

    def test_usb_paths_still_trigger_usb_semantics(self) -> None:
        files = [
            "packages/SystemUI/src/com/android/systemui/usb/UsbPermissionActivity.java",
            "ueventd.rc",
        ]
        modules = intake.patch_modules_from_files(files)
        problem, risk = intake.patch_problem_and_risk_payloads(
            "patch-usb",
            "patches/unisoc14-systemui@usb-default-permission.patch",
            "云外设 App USB 权限自动获取",
            {"modified_files": files, "modules": modules, "symbols": []},
        )

        self.assertIn("USB", modules)
        self.assertIn("USB", problem["problem_summary"])
        self.assertIn("USB/设备权限", risk["risk_areas"])

    def test_feature_capture_package_uses_one_feature_readme_for_multiple_patches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = prepare_patch_package(
                dt.date(2026, 6, 8),
                self.config(root),
                run_id="20260608-120000-feature",
                patch_paths=[],
                patch_package_paths=[str(create_feature_capture_package(root))],
                project="TVE1067M",
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
                    intake.PatchInfo(path=standalone_patch, name=standalone_patch.name, project="TVE1067M"),
                    self.config(root),
                    status="validated",
                    reuse_hint=True,
                ),
                encoding="utf-8",
            )

            package = prepare_patch_package(
                dt.date(2026, 6, 8),
                self.config(root),
                run_id="20260608-121000-template-companion",
                patch_paths=[str(standalone_patch)],
                patch_package_paths=[str(create_capture_package(root, workflow_contract="manual_import"))],
                project="TVE1067M",
                summary="功能级说明合格但补丁说明未补齐",
                status="validated",
                schema_version="1",
            )

            check = json.loads((package / "local-check.json").read_text(encoding="utf-8"))
            project_inference = json.loads((package / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))

            self.assertEqual(check["status"], "FAIL")
            self.assertTrue(any("template-companion.readme.md" in item and "TODO" in item for item in check["errors"]))
            self.assertFalse(any("TODO" in item for item in project_inference["payload"]["raw_inputs"]))

    def test_project_inference_normalizes_branch_suffix_to_project_model(self) -> None:
        project, payload = intake.infer_project(
            "unknown",
            [{"project": "TVE1067M1_H031", "path": "patches/mtk16-settings@lockscreen.patch"}],
            [],
            "",
        )

        self.assertEqual(project, "TVE1067M1")
        self.assertEqual(payload["base_model"], "TVE1067M1")
        self.assertEqual(payload["suffix"], "")
        self.assertTrue(payload["company_rule_match"])

    def test_project_inference_completes_missing_platform_letter_with_trusted_platform(self) -> None:
        project, payload = intake.infer_project(
            "unknown",
            [{"project": "TVE1213", "path": "patches/mtk14-frameworks-base@rotation.patch"}],
            [],
            "",
            trusted_platform="mtk",
        )

        self.assertEqual(project, "TVE1213M")
        self.assertEqual(payload["project"], "TVE1213M")
        self.assertEqual(payload["base_model"], "TVE1213M")
        self.assertTrue(payload["company_rule_match"])
        self.assertTrue(any("platform=mtk" in item and "TVE1213M" in item for item in payload["basis"]))

    def test_project_inference_accepts_tvi3315a_project_model(self) -> None:
        project, payload = intake.infer_project(
            "unknown",
            [{"project": "TVI3315A", "path": "patches/rk90-frameworks-base@industrial.patch"}],
            [],
            "",
            trusted_platform="rk",
        )

        self.assertEqual(project, "TVI3315A")
        self.assertEqual(payload["project"], "TVI3315A")
        self.assertEqual(payload["base_model"], "TVI3315A")
        self.assertEqual(payload["soc_code"], "A")
        self.assertTrue(payload["company_rule_match"])

    def test_project_inference_completes_tvi_short_model_with_chip_field(self) -> None:
        project, payload = intake.infer_project(
            "unknown",
            [{"project": "TVI3315", "path": "patches/rk90-frameworks-base@industrial.patch"}],
            [],
            "",
            trusted_platform="rk",
        )

        self.assertEqual(project, "TVI3315A")
        self.assertNotEqual(project, "TVI3315R")
        self.assertEqual(payload["project"], "TVI3315A")
        self.assertEqual(payload["base_model"], "TVI3315A")
        self.assertEqual(payload["soc_code"], "A")
        self.assertTrue(payload["company_rule_match"])
        self.assertTrue(any("TVI 芯片字段" in item and "TVI3315A" in item for item in payload["basis"]))

    def test_project_inference_strips_any_nonstandard_suffix_from_structured_project(self) -> None:
        examples = [
            ("TVE1086U_MAIN_HANGYAN", "TVE1086U"),
            ("TVE1091U福建移动高清", "TVE1091U"),
            ("TVA10A2R-camera-policy", "TVA10A2R"),
        ]
        for raw_project, expected_project in examples:
            with self.subTest(raw_project=raw_project):
                project, payload = intake.infer_project(
                    raw_project,
                    [{"project": raw_project, "path": "patches/mtk15-frameworks-base@feature.patch"}],
                    [],
                    f"{raw_project} display policy",
                )

                self.assertEqual(project, expected_project)
                self.assertEqual(payload["project"], expected_project)
                self.assertEqual(payload["base_model"], expected_project)
                self.assertEqual(payload["suffix"], "")
                self.assertTrue(payload["company_rule_match"])
                self.assertIn(raw_project, " ".join(payload["raw_inputs"]))

    def test_project_inference_normalizes_confirmed_project_alias(self) -> None:
        project, payload = intake.infer_project(
            "TVE8402",
            [],
            [],
            "",
        )

        self.assertEqual(project, "TVE8402M")
        self.assertEqual(payload["project"], "TVE8402M")
        self.assertEqual(payload["base_model"], "TVE8402M")
        self.assertEqual(payload["suffix"], "")
        self.assertTrue(payload["company_rule_match"])

    def test_project_inference_rejects_invalid_project_model(self) -> None:
        project, payload = intake.infer_project(
            "TVE1234A",
            [],
            [],
            "",
        )

        self.assertEqual(project, "unknown")
        self.assertEqual(payload["project"], "unknown")
        self.assertFalse(payload["company_rule_match"])

    def test_project_inference_accepts_tvi_scope(self) -> None:
        project, payload = intake.infer_project(
            "TVI3366R_H031",
            [],
            [],
            "",
        )

        self.assertEqual(project, "TVI3366R")
        self.assertEqual(payload["project"], "TVI3366R")
        self.assertEqual(payload["base_model"], "TVI3366R")
        self.assertEqual(payload["suffix"], "")
        self.assertTrue(payload["company_rule_match"])

        arm_project, arm_payload = intake.infer_project(
            "TVI3315A_H031",
            [],
            [],
            "",
        )
        self.assertEqual(arm_project, "TVI3315A")
        self.assertEqual(arm_payload["project"], "TVI3315A")
        self.assertTrue(arm_payload["company_rule_match"])

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
        self.assertEqual(payload["limits"], [])
        self.assertIn("TVE1067M1_H031", " ".join(payload["raw_inputs"]))

    def test_project_inference_keeps_m_and_m1_as_distinct_projects(self) -> None:
        project, payload = intake.infer_report_project(
            "daily",
            "今天同时提到 TVE1067M 和 TVE1067M1 两个不同项目。",
            {
                "TVE1067M": [("旧项目问题", "已完成")],
                "TVE1067M1": [("新项目问题", "已完成")],
            },
            [],
            [],
        )

        self.assertEqual(project, "unknown")
        self.assertIn("TVE1067M", payload["candidates"])
        self.assertIn("TVE1067M1", payload["candidates"])
        self.assertIn("多个项目型号", " ".join(payload["limits"]))

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

            package = prepare_patch_package(
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

    def test_patch_project_inference_uses_same_day_unique_daily_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.config(root)
            daily = Path(config["out_dir"]) / "submitted" / "20260612" / "admin_alias" / "20260612-210000-daily"
            (daily / "materials" / "evidence").mkdir(parents=True)
            write_json(
                daily / "manifest.json",
                {
                    "schema": "knowledge-incoming-package",
                    "schema_version": "1",
                    "package_kind": "daily_trace",
                    "member_alias": "admin_alias",
                    "member_name": "Member One",
                    "date": "2026-06-12",
                    "run_id": "20260612-210000-daily",
                    "project": "TVE8801M",
                    "summary": "今天处理 TVE8801M 导航模式任务栏固定像素。",
                    "files": {"evidence": ["materials/evidence/project_inference.json"]},
                },
            )
            write_json(
                daily / "materials" / "evidence" / "project_inference.json",
                {
                    "kind": "project_inference",
                    "payload": {
                        "project": "TVE8801M",
                        "recognized": True,
                        "basis": ["日报上下文: 今天处理 TVE8801M 导航模式任务栏固定像素。"],
                    },
                },
            )
            capture_package = create_capture_package(
                root,
                project="unknown",
                source_root="/home/cong/work/mtk/b_mt8775_8792_tablet",
                git_branch="master",
            )

            package = prepare_patch_package(
                dt.date(2026, 6, 12),
                config,
                run_id="20260612-230000-patch",
                patch_paths=[],
                patch_package_paths=[str(capture_package)],
                project="unknown",
                summary="导航模式任务栏固定像素",
                status="candidate",
                schema_version="1",
            )

            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            variant = json.loads((package / "materials" / "variant.json").read_text(encoding="utf-8"))
            project_inference = json.loads((package / "materials" / "evidence" / "project_inference.json").read_text(encoding="utf-8"))

            self.assertEqual(manifest["project"], "TVE8801M")
            self.assertEqual(variant["project"], "TVE8801M")
            self.assertEqual(manifest["related_report_run_ids"], ["20260612-210000-daily"])
            self.assertEqual(project_inference["payload"]["project"], "TVE8801M")
            self.assertIn("自动关联同日日报", " ".join(project_inference["payload"]["basis"]))


if __name__ == "__main__":
    unittest.main()
