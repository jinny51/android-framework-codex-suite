import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]


class ReportSkillSplitMetadataTests(unittest.TestCase):
    def test_android_framework_ops_exposes_split_member_intake_skills(self) -> None:
        expected = {
            "android-framework-patch-intake": "补丁包",
            "android-daily-report-intake": "日报",
            "android-weekly-report-intake": "周报",
        }

        manifest_text = (REPO_ROOT / "manifests" / "android-framework-ops.toml").read_text(encoding="utf-8")
        plugin_json = json.loads((REPO_ROOT / "plugins" / "android-framework-ops" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        plugin_readme = (REPO_ROOT / "plugins" / "android-framework-ops" / "README.md").read_text(encoding="utf-8")

        self.assertEqual(plugin_json["version"], "1.0.90")
        for skill_name, business_label in expected.items():
            skill_dir = REPO_ROOT / "plugins" / "android-framework-ops" / "skills" / skill_name
            self.assertTrue((skill_dir / "SKILL.md").is_file(), skill_name)
            self.assertTrue((skill_dir / "agents" / "openai.yaml").is_file(), skill_name)
            self.assertTrue((REPO_ROOT / "docs" / "skills" / "android-framework-ops" / skill_name / "README.md").is_file(), skill_name)
            skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
            agent_text = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
            self.assertIn(f"name: {skill_name}", skill_text)
            self.assertIn(f"${skill_name}", agent_text)
            self.assertIn(skill_name, manifest_text)
            self.assertIn(skill_name, plugin_readme)
            self.assertIn(business_label, skill_text)

        intake_text = (REPO_ROOT / "plugins" / "android-framework-ops" / "skills" / "android-knowledge-intake" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("兼容命令入口", intake_text)
        self.assertNotIn("legacy command", intake_text)
        self.assertIn("共享内核", intake_text)
        self.assertIn("android-daily-report-intake", intake_text)
        self.assertIn("android-weekly-report-intake", intake_text)
        self.assertIn("android-framework-patch-intake", intake_text)
