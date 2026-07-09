from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "android-framework-ops"
EXPORT_SCRIPT = PLUGIN_ROOT / "scripts" / "export_akbs_validation_rules.py"


class RulesExportTest(unittest.TestCase):
    def test_export_generates_importable_server_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            result = subprocess.run(
                [
                    sys.executable,
                    str(EXPORT_SCRIPT),
                    "--output-dir",
                    str(output_dir),
                    "--source-commit",
                    "test-source-commit",
                ],
                cwd=PLUGIN_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            generated = output_dir / "akbs_validation_rules.py"
            self.assertIn(str(generated), result.stdout)
            text = generated.read_text(encoding="utf-8")
            self.assertIn("GENERATED FROM android_framework_ops.knowledge_rules", text)
            self.assertIn("android-framework-ops 1.0.95", text)
            self.assertIn("AKBS_RULES_CONTRACT_VERSION", text)
            self.assertIn("test-source-commit", text)
            self.assertNotIn("/home/jinny", text)
            self.assertNotIn("/mnt/c/Users", text)
            self.assertNotIn(".codex/plugins/cache", text)

            spec = importlib.util.spec_from_file_location("generated_akbs_validation_rules", generated)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            self.assertEqual(module.current_plugin_version(), "1.0.95")
            self.assertEqual(module.AKBS_RULES_CONTRACT_VERSION, "2026-07-02.1")
            self.assertEqual(module.find_company_project("project: TVE1213", platform="mtk"), "TVE1213M")
            self.assertEqual(module.find_company_project("project: TVI3315", platform="rk"), "TVI3315A")
            self.assertEqual(
                module.source_version_compatibility_matrix()["lightweight_supplement_v1"]["min_plugin_version"],
                "1.0.65",
            )


if __name__ == "__main__":
    unittest.main()
