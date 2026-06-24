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
        self.assertFalse(valid_project_model("app15"))

        parsed = parse_company_project("TVE1067M1")
        self.assertEqual(parsed["base_model"], "TVE1067M1")
        self.assertEqual(parsed["mold_code"], "1067")
        self.assertEqual(parsed["soc_code"], "M")
        self.assertEqual(parsed["extension_code"], "1")

    def test_platform_and_android_version_token_contract(self) -> None:
        from android_framework_ops.knowledge_rules import (
            find_platform_tokens,
            has_uncontrolled_app_patch_asset_prefix,
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


if __name__ == "__main__":
    unittest.main()
