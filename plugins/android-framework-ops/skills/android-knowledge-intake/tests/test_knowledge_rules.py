from __future__ import annotations

import sys
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_LIB = PLUGIN_ROOT / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))


class KnowledgeRulesTest(unittest.TestCase):
    def test_project_model_normalization_contract(self) -> None:
        from android_framework_ops.knowledge_rules import (
            complete_company_project_with_platform,
            find_company_project,
            find_company_projects,
            parse_company_project,
            valid_project_model,
        )

        self.assertEqual(find_company_project("TVE1067M1_H031"), "TVE1067M1")
        self.assertEqual(find_company_project("TVE1086U_MAIN_HANGYAN"), "TVE1086U")
        self.assertEqual(find_company_project("TVE1091U福建移动高清"), "TVE1091U")
        self.assertEqual(find_company_project("TVE8402"), "TVE8402M")
        self.assertEqual(find_company_projects("TVE1067M TVE1067M1 TVE1067M1_H031"), ["TVE1067M", "TVE1067M1"])
        self.assertTrue(valid_project_model("TVA10A2R"))
        self.assertTrue(valid_project_model("TVE10A2R"))
        self.assertTrue(valid_project_model("TVE1067M1"))
        self.assertFalse(valid_project_model("TVE1234A"))
        self.assertFalse(valid_project_model("TVE1213"))
        self.assertFalse(valid_project_model("app15"))
        self.assertEqual(complete_company_project_with_platform("TVE1213", "mtk"), "TVE1213M")
        self.assertEqual(complete_company_project_with_platform("TVA10A2", "rk"), "TVA10A2R")
        self.assertEqual(complete_company_project_with_platform("TVI3315", "rk"), "TVI3315A")
        self.assertEqual(complete_company_project_with_platform("TVI3315", "rk", evidence_text="x86 工控主板"), "TVI3315X")
        self.assertNotEqual(complete_company_project_with_platform("TVI3315", "rk"), "TVI3315R")
        self.assertEqual(complete_company_project_with_platform("TVE1213", ""), "")
        self.assertEqual(complete_company_project_with_platform("TVE12", "mtk"), "")
        self.assertEqual(find_company_project("project: TVE1213", platform="mtk"), "TVE1213M")
        self.assertEqual(find_company_project("project: TVE1213"), "")
        self.assertEqual(find_company_projects("TVE1213 TVA10A2", platform="rk"), ["TVA10A2R", "TVE1213R"])
        self.assertTrue(valid_project_model("TVI3315A"))
        self.assertTrue(valid_project_model("TVI3315X"))
        self.assertTrue(valid_project_model("TVI3366R"))
        self.assertEqual(find_company_project("project: TVI3315A", platform="rk"), "TVI3315A")
        self.assertEqual(find_company_project("project: TVI3315X", platform="rk"), "TVI3315X")
        self.assertEqual(find_company_project("project: TVI3366R", platform="mtk"), "TVI3366R")
        self.assertEqual(find_company_project("TVI3315A-camera-policy", platform="rk"), "TVI3315A")
        self.assertEqual(find_company_project("project: TVI3315", platform="rk"), "TVI3315A")
        self.assertEqual(find_company_project("project: TVI3315 x86", platform="rk"), "TVI3315X")
        self.assertEqual(find_company_projects("TVI3315", platform="rk"), ["TVI3315A"])

        parsed = parse_company_project("TVE1067M1")
        self.assertEqual(parsed["base_model"], "TVE1067M1")
        self.assertEqual(parsed["mold_code"], "1067")
        self.assertEqual(parsed["soc_code"], "M")
        self.assertEqual(parsed["extension_code"], "1")

        parsed_tvi = parse_company_project("TVI3315A")
        self.assertEqual(parsed_tvi["base_model"], "TVI3315A")
        self.assertEqual(parsed_tvi["mold_code"], "3315")
        self.assertEqual(parsed_tvi["soc_code"], "A")
        self.assertEqual(parsed_tvi["extension_code"], "")

    def test_platform_and_android_version_token_contract(self) -> None:
        from android_framework_ops.knowledge_rules import (
            find_platform_tokens,
            has_uncontrolled_app_patch_asset_prefix,
            has_uncontrolled_patch_asset_prefix,
            is_valid_android_version_value,
            is_valid_platform_value,
            parse_known_platform_token,
            parse_version_only_token,
        )

        self.assertEqual(parse_known_platform_token("mtk15-frameworks-base@wifi.patch"), ("mtk", "15"))
        self.assertEqual(parse_known_platform_token("rk90-frameworks-base@taskbar.patch"), ("rk", "9.0"))
        self.assertEqual(parse_known_platform_token("u14-frameworks-base@permission.patch"), ("unisoc", "14"))
        self.assertEqual(parse_known_platform_token("sprd14-frameworks-base@permission.patch"), ("unisoc", "14"))
        self.assertEqual(parse_known_platform_token("app15-frameworks-base@permission.patch"), ("", ""))
        self.assertEqual(parse_version_only_token("app15-frameworks-base@permission.patch"), "15")
        self.assertEqual(parse_version_only_token("android14-frameworks-base@permission.patch"), "14")
        self.assertEqual(find_platform_tokens("平台 mtk15，另有 rk9 旧实现"), [("mtk", "15"), ("rk", "9")])
        self.assertTrue(is_valid_platform_value("unknown"))
        self.assertTrue(is_valid_platform_value("unisoc"))
        self.assertFalse(is_valid_platform_value("app"))
        self.assertTrue(is_valid_android_version_value("9.0"))
        self.assertFalse(is_valid_android_version_value("app15"))
        self.assertTrue(has_uncontrolled_app_patch_asset_prefix("app15-frameworks-base@permission.patch"))
        self.assertTrue(has_uncontrolled_patch_asset_prefix("app15-frameworks-base@permission.patch"))
        self.assertTrue(has_uncontrolled_patch_asset_prefix("android16-frameworks-base@permission.patch"))
        self.assertTrue(has_uncontrolled_patch_asset_prefix("Camera2-frameworks-base@permission.patch"))
        self.assertFalse(has_uncontrolled_patch_asset_prefix("mtk15-frameworks-base@permission.patch"))
        self.assertFalse(has_uncontrolled_patch_asset_prefix("rk90-frameworks-base@permission.patch"))
        self.assertFalse(has_uncontrolled_patch_asset_prefix("TVE1067M1-frameworks-base@permission.patch"))

    def test_pre_change_search_classification_contract(self) -> None:
        from android_framework_ops.knowledge_rules import classify_pre_change_search

        manual = classify_pre_change_search(
            {"searched": False, "decision": "unknown"},
            implementation_origin="manual",
            package_status="validated",
        )
        self.assertFalse(manual["member_can_supplement"])
        self.assertTrue(manual["requires_post_change_overlap_check"])
        self.assertEqual(manual["validity_score_effect"], "no_search_loop_score")

        codex_unknown = classify_pre_change_search(
            {"searched": True, "results": ["case-taskbar"], "decision": "unknown"},
            implementation_origin="codex",
            package_status="validated",
        )
        self.assertTrue(codex_unknown["member_can_supplement"])
        self.assertEqual(codex_unknown["missing_field"], "search_usage")

        codex_closed = classify_pre_change_search(
            {"searched": True, "results": ["case-taskbar"], "decision": "adapt"},
            implementation_origin="codex",
            package_status="validated",
        )
        self.assertFalse(codex_closed["member_can_supplement"])
        self.assertFalse(codex_closed["requires_post_change_overlap_check"])

    def test_source_version_contract_requires_current_plugin_version(self) -> None:
        from android_framework_ops.knowledge_rules import current_plugin_version, source_version_errors

        current = current_plugin_version()
        self.assertEqual(current, "1.0.62")
        self.assertEqual(
            source_version_errors(
                {
                    "plugin_name": "android-framework-ops",
                    "plugin_version": current,
                    "skill_version": current,
                }
            ),
            [],
        )
        stale_errors = source_version_errors(
            {
                "plugin_name": "android-framework-ops",
                "plugin_version": "1.0.43",
                "skill_version": "1.0.43",
            }
        )
        self.assertIn(f"source evidence plugin_version must match current plugin version {current}", stale_errors)
        self.assertIn(f"source evidence skill_version must match current plugin version {current}", stale_errors)

    def test_supplement_field_policy_contract(self) -> None:
        from android_framework_ops.knowledge_rules import supplement_field_policy

        project = supplement_field_policy("project")
        self.assertTrue(project["member_can_supplement"])
        self.assertFalse(project["historical_fact"])
        self.assertIn("项目", project["member_label"])

        search = supplement_field_policy("search_usage")
        self.assertFalse(search["member_can_fabricate"])
        self.assertTrue(search["historical_fact"])
        self.assertIn("不能事后补造", search["guidance"])

    def test_patch_asset_name_classification_contract(self) -> None:
        from android_framework_ops.knowledge_rules import classify_patch_asset_names

        result = classify_patch_asset_names(
            [
                "app15-frameworks-base@wifi.patch",
                "Camera2-frameworks-base@wifi.patch",
                "TVE1067M1-frameworks-base@wifi.patch",
                "mtk15-frameworks-base@wifi.patch",
            ]
        )
        self.assertIn("patch_asset_pollution", result["issue_codes"])
        self.assertIn("app15-frameworks-base@wifi.patch", result["uncontrolled_prefixes"])
        self.assertIn("Camera2-frameworks-base@wifi.patch", result["uncontrolled_prefixes"])
        self.assertNotIn("TVE1067M1-frameworks-base@wifi.patch", result["uncontrolled_prefixes"])
        self.assertNotIn("mtk15-frameworks-base@wifi.patch", result["uncontrolled_prefixes"])

    def test_template_leak_contract_blocks_camera_text_for_eink_package(self) -> None:
        from android_framework_ops.knowledge_rules import template_leak_errors

        errors = template_leak_errors(
            summary="E-Ink 显示模式补丁资产修正",
            problem="相机预览、扫码、拍照或相机权限行为可能不符合产品要求。",
            solution="调整 CameraService、Camera2 或相机 HAL 相关路径，并验证目标相机场景。",
            patch_paths=["patches/rk14-frameworks-base@eink-display-mode.patch"],
            modified_files=["frameworks/base/core/res/res/values/config.xml"],
        )

        self.assertTrue(errors)
        self.assertIn("模板文本泄漏", errors[0])
        self.assertIn("相机", errors[0])

        camera_errors = template_leak_errors(
            summary="Camera2 reversePortrait 方向补偿",
            problem="相机预览、扫码、拍照或相机权限行为可能不符合产品要求。",
            solution="调整 CameraService、Camera2 或相机 HAL 相关路径，并验证目标相机场景。",
            patch_paths=["patches/mtk16-camera2@reverseportrait.patch"],
            modified_files=["frameworks/av/services/camera/libcameraservice/CameraService.cpp"],
        )

        self.assertEqual(camera_errors, [])

    def test_patch_upload_gate_requires_validated_status_by_default(self) -> None:
        from android_framework_ops.knowledge_rules import patch_upload_gate_errors

        candidate_errors = patch_upload_gate_errors(
            {
                "package_kind": "framework_change",
                "package_status": "candidate",
                "summary": "导航策略调整",
            }
        )

        self.assertTrue(candidate_errors)
        self.assertIn("普通补丁包", candidate_errors[0])
        self.assertIn("已验证（validated）", candidate_errors[0])

        validated_errors = patch_upload_gate_errors(
            {
                "package_kind": "framework_change",
                "package_status": "validated",
                "summary": "导航策略调整",
            }
        )

        self.assertEqual(validated_errors, [])

    def test_supplement_target_relation_blocks_nested_supplement(self) -> None:
        from android_framework_ops.knowledge_rules import patch_upload_gate_errors, supplement_target_relation_errors

        relation_errors = supplement_target_relation_errors(
            "20260625/wangwei/20260625-221500-verification-supplement"
        )

        self.assertTrue(relation_errors)
        self.assertIn("不能继续补证补证包", relation_errors[0])
        self.assertIn("原始包", relation_errors[0])

        upload_errors = patch_upload_gate_errors(
            {
                "package_kind": "framework_change",
                "package_status": "validated",
                "supplement_for_package_key": "20260625/wangwei/20260625-221500-verification-supplement",
            }
        )

        self.assertTrue(upload_errors)
        self.assertIn("不能继续补证补证包", "\n".join(upload_errors))

    def test_function_scope_classification_contract(self) -> None:
        from android_framework_ops.knowledge_rules import classify_function_scope

        good = classify_function_scope(
            "基于同一 PCMODE 功能目标，拆分系统界面、快捷设置和任务栏三个子改动。",
            patch_count=3,
        )
        self.assertEqual(good["status"], "pass")

        bad = classify_function_scope(
            "今日补丁：HD 版本云电脑跳转逻辑、系统弹窗副屏显示、移除 Alt+Tab 最近任务组合键。",
            patch_count=3,
        )
        self.assertEqual(bad["status"], "fail")
        self.assertIn("aggregate_package", bad["issue_codes"])

    def test_curation_text_missing_fields_prefers_patch_asset_correction_over_conditional_split(self) -> None:
        from android_framework_ops.knowledge_rules import curation_text_missing_fields

        fields = curation_text_missing_fields(
            "沉淀依据：补丁资产污染，需要补丁资产修正（patch asset correction），"
            "请在干净工作树重新采集同一功能补丁包。"
            "这不是按功能拆分（function split）问题。"
            "如果实际是多个独立功能，再按功能拆分补丁包（function split）。"
        )

        self.assertEqual(fields, ["patch_asset_correction"])

        aggregate_fields = curation_text_missing_fields(
            "沉淀依据：该包是今日补丁合集，包含多个独立功能，必须按功能拆分补丁包。"
        )

        self.assertEqual(aggregate_fields, ["function_split"])

    def test_upload_text_and_run_id_quality_contract(self) -> None:
        import datetime as dt

        from android_framework_ops.knowledge_rules import future_run_id_errors, text_field_quality_errors

        text_errors = text_field_quality_errors(
            {
                "manifest.summary": "?????????????",
                "manifest.supplement_reason": "?????verification???",
            }
        )
        self.assertEqual(len(text_errors), 2)
        self.assertIn("问号乱码", text_errors[0])

        time_errors = future_run_id_errors(
            "20260625-160100-patch",
            now=dt.datetime(2026, 6, 25, 15, 52, 57),
            tolerance_seconds=60,
        )
        self.assertEqual(len(time_errors), 1)
        self.assertIn("晚于服务器当前时间", time_errors[0])


if __name__ == "__main__":
    unittest.main()
