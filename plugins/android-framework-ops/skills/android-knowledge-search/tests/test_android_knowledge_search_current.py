from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import android_knowledge_search as search


class FakeHttpResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


class AndroidKnowledgeSearchCurrentTests(unittest.TestCase):
    def make_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        write_jsonl(root / "index" / "case-index.jsonl", [])
        write_jsonl(root / "index" / "variant-index.jsonl", [])
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_jsonl(root / "index" / "evidence-index.jsonl", [])
        write_json(
            root / "events" / "by-id" / "event-power.json",
            {
                "schema": "knowledge-event",
                "event_id": "event-power",
                "event_type": "incoming",
                "source_type": "incoming_package",
                "package_kind": "framework_change",
                "package_status": "validated",
                "member_alias": "testuser",
                "member_name": "测试成员",
                "date": "2026-05-26",
                "project": "TVE8402M",
                "platform": "rk3576",
                "summary": "修改电源键策略以满足产品需求",
            },
        )
        verification_evidence = {
            "schema": "knowledge-evidence",
            "evidence_id": "verification-result",
            "case_id": "case-power-key",
            "variant_id": "variant-rk3576-tve8402m-power-key",
            "kind": "verification_result",
            "result": "PASS",
            "summary": "rk3576 真机验证电源键行为通过",
            "payload": {"method": "device", "device": "rk3576"},
        }
        write_json(root / "evidence" / "by-id" / "verification-result.json", verification_evidence)
        write_jsonl(root / "index" / "evidence-index.jsonl", [verification_evidence])
        write_json(
            root / "evidence" / "by-id" / "source-evidence.json",
            {
                "schema": "knowledge-evidence",
                "evidence_id": "source-evidence",
                "event_id": "event-power",
                "kind": "source",
                "summary": "成员会话原始材料包含密码123等归档内容",
                "payload": {"raw_text": "密码123 电源键排查过程"},
            },
        )
        write_json(
            root / "reports" / "by-id" / "report-power.json",
            {
                "schema": "knowledge-report",
                "report_id": "report-power",
                "type": "daily",
                "author": "测试成员",
                "date": "2026-05-26",
                "overview": "密码123 电源键日报记录",
                "items": [{"title": "电源键调试", "project": "TVE8402M"}],
            },
        )
        return root

    def test_default_load_rows_excludes_archive_rows(self):
        root = self.make_root()

        rows = search.load_rows(root)

        kinds = {row["kind"] for row in rows}
        self.assertIn("evidence", kinds)
        self.assertNotIn("event", kinds)
        self.assertNotIn("report", kinds)
        self.assertNotIn("source-evidence", {row.get("id") for row in rows})

    def test_find_root_uses_configured_knowledge_worktree_without_database_worktree(self):
        temp = Path(tempfile.mkdtemp())
        codex_home = temp / ".codex"
        knowledge_root = codex_home / "worktrees" / "knowledge"
        (knowledge_root / "index").mkdir(parents=True)
        write_jsonl(knowledge_root / "index" / "case-index.jsonl", [])
        config_dir = codex_home / "report"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            """
            default_profile = "member01"

            [profiles.member01]
            member_alias = "member01"
            member_name = "成员一"
            knowledge_repo_worktree = "$CODEX_HOME/worktrees/knowledge"
            """,
            encoding="utf-8",
        )

        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(codex_home),
                "CODEX_REPORT_PROFILE": "member01",
                "CODEX_KNOWLEDGE_ROOT": "",
                "CODEX_KNOWLEDGE_REPO_WORKTREE": "",
                "CODEX_REPORT_KNOWLEDGE_REPO_WORKTREE": "",
            },
        ):
            candidates = search.candidate_roots(None)
            root = search.find_root(None)

        candidate_text = "\n".join(str(item) for item in candidates)
        self.assertEqual(root, knowledge_root.resolve())
        self.assertNotIn("knowledge-" + "jinny", candidate_text)
        self.assertNotIn("knowledge-" + "test", candidate_text)

    def test_search_can_filter_event_and_evidence(self):
        root = self.make_root()
        rows = search.load_rows(root, include_archive=True)

        events = search.search(rows, "电源键 rk3576", "event", 5, include_synthetic=False)
        evidence = search.search(rows, "真机验证", "evidence", 5, include_synthetic=False)

        self.assertEqual(events[0]["id"], "event-power")
        self.assertEqual(evidence[0]["id"], "verification-result")

    def test_default_search_excludes_archive_rows_but_keeps_ai_evidence(self):
        root = self.make_root()
        rows = search.load_rows(root)
        results = search.search(rows, "电源键 真机验证", "all", 5, include_synthetic=False)

        text = search.format_markdown(root, "电源键 真机验证", results, None)

        self.assertIn("[evidence]", text)
        self.assertNotIn("[event]", text)
        self.assertNotIn("[report]", text)

        archive_results = search.search(rows, "密码123", "all", 5, include_synthetic=False)
        self.assertEqual(archive_results, [])

    def test_default_search_redacts_retracted_references_inside_evidence_payloads(self):
        root = self.make_root()
        write_jsonl(
            root / "index" / "case-index.jsonl",
            [
                {
                    "case_id": "case-retracted",
                    "title": "通知栏音量弹窗位置适配",
                    "status": "retracted",
                    "knowledge_validity": {"retracted": True},
                },
                {
                    "case_id": "case-active",
                    "title": "分屏导航栏高度修复",
                    "status": "needs_review",
                    "knowledge_validity": {"confidence": "medium"},
                },
            ],
        )
        write_jsonl(
            root / "index" / "search-docs.jsonl",
            [
                {
                    "case_id": "case-active",
                    "title": "分屏导航栏高度修复",
                    "text": "gesture nav split screen",
                    "status": "needs_review",
                }
            ],
        )
        write_jsonl(
            root / "index" / "evidence-index.jsonl",
            [
                {
                    "schema": "knowledge-evidence",
                    "evidence_id": "evidence-search-usage",
                    "case_id": "case-active",
                    "variant_id": "variant-active",
                    "kind": "search_before_change",
                    "summary": "成员侧搜索记录",
                    "payload": {
                        "best_match": "case-retracted",
                        "results": [
                            "case case-retracted / 通知栏音量弹窗位置适配",
                            "variant case-retracted",
                            "case case-active / 分屏导航栏高度修复",
                        ],
                        "targets": ["case-retracted", "case-active"],
                    },
                }
            ],
        )

        rows = search.load_rows(root)
        default_results = search.search(rows, "通知栏音量弹窗", "all", 5, include_synthetic=False)
        evidence = next(row for row in rows if row.get("id") == "evidence-search-usage")

        self.assertEqual(default_results, [])
        self.assertEqual(evidence["payload"]["best_match"], "")
        self.assertEqual(evidence["payload"]["results"], ["case case-active / 分屏导航栏高度修复"])
        self.assertEqual(evidence["payload"]["targets"], ["case-active"])

        archive_rows = search.load_rows(root, include_archive=True)
        archive_evidence = next(row for row in archive_rows if row.get("id") == "evidence-search-usage")
        self.assertIn("case case-retracted / 通知栏音量弹窗位置适配", archive_evidence["payload"]["results"])

    def test_explicit_archive_filters_remain_available(self):
        root = self.make_root()
        rows = search.load_rows(root, include_archive=True)

        reports = search.search(rows, "密码123", "report", 5, include_synthetic=False)
        events = search.search(rows, "电源键 rk3576", "event", 5, include_synthetic=False)
        evidence = search.search(rows, "密码123", "evidence", 5, include_synthetic=False)

        self.assertEqual(reports[0]["id"], "report-power")
        self.assertEqual(events[0]["id"], "event-power")
        self.assertEqual(evidence[0]["id"], "source-evidence")

    def test_main_records_member_search_usage_by_default(self):
        root = self.make_root()
        temp = Path(tempfile.mkdtemp())
        codex_home = temp / "codex-home"
        out_dir = temp / "artifacts" / "android-knowledge-intake"
        config_dir = codex_home / "report"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            f"""
            default_profile = "member01"

            [paths]
            out_dir = "{out_dir.as_posix()}"

            [profiles.member01]
            member_alias = "member01"
            member_name = "成员一"
            """,
            encoding="utf-8",
        )

        with patch.dict(os.environ, {"CODEX_HOME": str(codex_home), "CODEX_REPORT_PROFILE": "member01"}):
            with patch("sys.stdout", new=io.StringIO()):
                code = search.main(
                    [
                        "--root",
                        str(root),
                        "--json",
                        "--reuse-decision",
                        "adapt",
                        "--reuse-target",
                        "case-power-key",
                        "--reuse-reason",
                        "同类电源键策略可以参考，但当前项目需要适配",
                        "电源键",
                        "rk3576",
                    ]
                )

        self.assertEqual(code, 0)
        records = list((out_dir / "search-usage").rglob("*.json"))
        self.assertEqual(len(records), 1)
        payload = json.loads(records[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "android-knowledge-search-usage")
        self.assertEqual(payload["member_alias"], "member01")
        self.assertEqual(payload["query"], "电源键 rk3576")
        self.assertEqual(payload["decision"], "adapt")
        self.assertEqual(payload["reuse_decision"], "adapt")
        self.assertEqual(payload["targets"], ["case-power-key"])
        self.assertGreater(payload["result_count"], 0)

    def test_main_prefers_server_hybrid_search_for_reusable_results(self):
        temp = Path(tempfile.mkdtemp())
        codex_home = temp / "codex-home"
        out_dir = temp / "artifacts" / "android-knowledge-intake"
        config_dir = codex_home / "report"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            f"""
            default_profile = "member01"

            [paths]
            out_dir = "{out_dir.as_posix()}"

            [profiles.member01]
            member_alias = "member01"
            member_name = "成员一"
            """,
            encoding="utf-8",
        )
        payload = {
            "schema": "akbs-member-knowledge-search-v1",
            "search_mode": "hybrid",
            "results": [
                {
                    "title": "电源键策略复用",
                    "summary": "已有同功能可复用实现",
                    "reuse_grade": "reusable",
                    "case_id": "case-power-key",
                    "matched_channels": ["semantic", "symbol"],
                    "matched_anchors": ["PowerManagerService", "电源键"],
                }
            ],
        }
        seen_headers = {}

        def fake_urlopen(request, timeout=0):
            seen_headers["user"] = request.get_header("X-akbs-user")
            seen_headers["role"] = request.get_header("X-akbs-role")
            return FakeHttpResponse(payload)

        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(codex_home),
                "CODEX_REPORT_PROFILE": "member01",
                "CODEX_REPORT_AKBS_ENDPOINT_MEMBER_SEARCH_URL": "http://akbs.invalid/akbs/api/member/knowledge-search",
            },
        ):
            stdout = io.StringIO()
            with patch("urllib.request.urlopen", fake_urlopen), patch("sys.stdout", new=stdout):
                code = search.main(["电源键", "PowerManagerService"])

        self.assertEqual(code, 0)
        text = stdout.getvalue()
        self.assertIn("server_hybrid", text)
        self.assertIn("可复用候选", text)
        self.assertIn("电源键策略复用", text)
        self.assertEqual(seen_headers["user"], "member01")
        self.assertEqual(seen_headers["role"], "member")

        records = list((out_dir / "search-usage").rglob("*.json"))
        self.assertEqual(len(records), 1)
        usage = json.loads(records[0].read_text(encoding="utf-8"))
        self.assertEqual(usage["source"], "server_hybrid")
        self.assertEqual(usage["search_mode"], "hybrid")
        self.assertEqual(usage["results"][0]["reuse_grade"], "reusable")
        self.assertEqual(usage["results"][0]["matched_channels"], ["semantic", "symbol"])
        self.assertEqual(usage["results"][0]["matched_anchors"], ["PowerManagerService", "电源键"])

    def test_server_reference_only_is_not_displayed_as_reusable(self):
        payload = {
            "schema": "akbs-member-knowledge-search-v1",
            "search_mode": "hybrid",
            "results": [
                {
                    "title": "宽泛代码锚点",
                    "summary": "只有单个宽泛锚点命中",
                    "reuse_grade": "reference_only",
                    "case_id": "case-reference",
                    "matched_channels": ["code_anchor"],
                    "matched_anchors": ["SettingsProvider"],
                }
            ],
        }

        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(Path(tempfile.mkdtemp()) / "codex-home"),
                "CODEX_REPORT_AKBS_ENDPOINT_MEMBER_SEARCH_URL": "http://akbs.invalid/akbs/api/member/knowledge-search",
            },
        ):
            stdout = io.StringIO()
            with patch("urllib.request.urlopen", return_value=FakeHttpResponse(payload)), patch("sys.stdout", new=stdout):
                code = search.main(["SettingsProvider"])

        self.assertEqual(code, 0)
        text = stdout.getvalue()
        self.assertIn("仅参考", text)
        self.assertNotIn("可复用候选", text)

    def test_json_output_keeps_server_fields_and_source_metadata(self):
        payload = {
            "schema": "akbs-member-knowledge-search-v1",
            "search_mode": "hybrid",
            "results": [
                {
                    "title": "电源键策略复用",
                    "reuse_grade": "reusable",
                    "case_id": "case-power-key",
                    "package_id": "pkg-power-key",
                    "matched_channels": ["semantic"],
                    "matched_anchors": ["PowerManagerService"],
                }
            ],
        }

        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(Path(tempfile.mkdtemp()) / "codex-home"),
                "CODEX_REPORT_AKBS_ENDPOINT_MEMBER_SEARCH_URL": "http://akbs.invalid/akbs/api/member/knowledge-search",
            },
        ):
            stdout = io.StringIO()
            with patch("urllib.request.urlopen", return_value=FakeHttpResponse(payload)), patch("sys.stdout", new=stdout):
                code = search.main(["--json", "电源键"])

        self.assertEqual(code, 0)
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["source"], "server_hybrid")
        self.assertEqual(output["search_mode"], "hybrid")
        self.assertEqual(output["fallback_reason"], "")
        self.assertEqual(output["results"][0]["reuse_grade"], "reusable")
        self.assertEqual(output["results"][0]["case_id"], "case-power-key")
        self.assertEqual(output["results"][0]["package_id"], "pkg-power-key")

    def test_member_config_without_server_fields_uses_default_endpoint_resolver(self):
        temp = Path(tempfile.mkdtemp())
        codex_home = temp / "codex-home"
        config_dir = codex_home / "report"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            """
            default_profile = "member01"

            [profiles.member01]
            member_alias = "member01"
            member_name = "成员一"
            role = "member"
            """,
            encoding="utf-8",
        )
        payload = {
            "schema": "akbs-member-knowledge-search-v1",
            "search_mode": "hybrid",
            "results": [],
        }
        seen_url = {}

        def fake_urlopen(request, timeout=0):
            seen_url["value"] = request.full_url
            return FakeHttpResponse(payload)

        with patch.dict(os.environ, {"CODEX_HOME": str(codex_home), "CODEX_REPORT_PROFILE": "member01"}, clear=True):
            stdout = io.StringIO()
            with patch("urllib.request.urlopen", fake_urlopen), patch("sys.stdout", new=stdout):
                code = search.main(["电源键"])

        self.assertEqual(code, 0)
        self.assertTrue(seen_url["value"].startswith("http://192.168.100.118:8088/akbs/api/member/knowledge-search?"))
        self.assertIn("q=", seen_url["value"])

    def test_server_unavailable_falls_back_to_local_jsonl_and_records_reason(self):
        root = self.make_root()
        temp = Path(tempfile.mkdtemp())
        codex_home = temp / "codex-home"
        out_dir = temp / "artifacts" / "android-knowledge-intake"
        config_dir = codex_home / "report"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(
            f"""
            default_profile = "member01"

            [paths]
            out_dir = "{out_dir.as_posix()}"

            [profiles.member01]
            member_alias = "member01"
            member_name = "成员一"
            """,
            encoding="utf-8",
        )

        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(codex_home),
                "CODEX_REPORT_PROFILE": "member01",
                "CODEX_REPORT_AKBS_ENDPOINT_MEMBER_SEARCH_URL": "http://akbs.invalid/akbs/api/member/knowledge-search",
            },
        ):
            stdout = io.StringIO()
            with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")), patch("sys.stdout", new=stdout):
                code = search.main(["--root", str(root), "电源键", "rk3576"])

        self.assertEqual(code, 0)
        text = stdout.getvalue()
        self.assertIn("local_jsonl_fallback", text)
        self.assertIn("本地文本搜索，未经过服务端 hybrid 分级", text)
        records = list((out_dir / "search-usage").rglob("*.json"))
        self.assertEqual(len(records), 1)
        usage = json.loads(records[0].read_text(encoding="utf-8"))
        self.assertEqual(usage["source"], "local_jsonl_fallback")
        self.assertEqual(usage["search_mode"], "local_jsonl")
        self.assertIn("offline", usage["fallback_reason"])

    def test_server_unauthorized_falls_back_to_local_jsonl(self):
        root = self.make_root()
        temp = Path(tempfile.mkdtemp())
        codex_home = temp / "codex-home"
        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(codex_home),
                "CODEX_REPORT_AKBS_ENDPOINT_MEMBER_SEARCH_URL": "http://akbs.invalid/akbs/api/member/knowledge-search",
            },
        ):
            stdout = io.StringIO()
            error = urllib.error.HTTPError("http://akbs.invalid", 401, "Unauthorized", None, None)
            with patch("urllib.request.urlopen", side_effect=error), patch("sys.stdout", new=stdout):
                code = search.main(["--root", str(root), "电源键"])

        self.assertEqual(code, 0)
        text = stdout.getvalue()
        self.assertIn("local_jsonl_fallback", text)
        self.assertIn("HTTP 401", text)

    def test_current_rebuild_case_and_variant_indexes_are_searchable(self):
        root = Path(tempfile.mkdtemp())
        write_jsonl(
            root / "index" / "case-index.jsonl",
            [
                {
                    "case_id": "case-volume-dialog",
                    "title": "通知音量弹窗位置适配",
                    "problem": "通知音量弹窗位置不符合项目要求",
                    "solution_summary": "调整 SystemUI 音量弹窗位置策略",
                    "variant_ids": ["variant-mtk15-tve8402m-volume-dialog"],
                    "source_priority": 100,
                }
            ],
        )
        write_jsonl(
            root / "index" / "variant-index.jsonl",
            [
                {
                    "variant_id": "variant-mtk15-tve8402m-volume-dialog",
                    "case_id": "case-volume-dialog",
                    "platform": "mtk",
                    "android_version": "15",
                    "project": "TVE8402M",
                    "repo_paths": ["vendor/mediatek/proprietary/packages/apps/SystemUI"],
                    "modified_files": ["src/com/android/systemui/volume/VolumeDialogImpl.java"],
                    "patch_ids": ["patch-abc"],
                    "report_ids": ["report-daily"],
                    "status": "candidate",
                    "verification": {"status": "missing", "method": "not_provided", "summary": "未提供验证证据"},
                }
            ],
        )
        write_jsonl(
            root / "index" / "search-docs.jsonl",
            [
                {
                    "type": "case",
                    "case_id": "case-volume-dialog",
                    "title": "通知音量弹窗位置适配",
                    "source_priority": 120,
                    "text": "通知音量弹窗位置适配\nSystemUI\nTVE8402M\nVolumeDialogImpl.java",
                    "variant_ids": ["variant-mtk15-tve8402m-volume-dialog"],
                }
            ],
        )
        write_jsonl(root / "index" / "evidence-index.jsonl", [])
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_json(
            root / "patches" / "by-id" / "patch-abc" / "patch.json",
            {
                "patch_id": "patch-abc",
                "case_id": "case-volume-dialog",
                "variant_id": "variant-mtk15-tve8402m-volume-dialog",
                "patch_name": "mtk15-systemui@volume-dialog-position.patch",
                "repo_paths": ["vendor/mediatek/proprietary/packages/apps/SystemUI"],
                "modified_files": ["src/com/android/systemui/volume/VolumeDialogImpl.java"],
                "status": "candidate",
            },
        )

        rows = search.load_rows(root)
        kinds = {row["kind"] for row in rows}
        self.assertIn("case", kinds)
        self.assertIn("variant", kinds)
        self.assertIn("patch", kinds)

        case_results = search.search(rows, "通知音量 SystemUI", "case", 5, include_synthetic=False)
        variant_results = search.search(rows, "TVE8402M VolumeDialogImpl", "variant", 5, include_synthetic=False)
        patch_results = search.search(rows, "volume-dialog-position", "patch", 5, include_synthetic=False)
        case_by_variant_terms = search.search(rows, "TVE8402M VolumeDialogImpl", "case", 5, include_synthetic=False)
        text = search.format_markdown(root, "TVE8402M VolumeDialogImpl", variant_results, None)

        self.assertEqual(case_results[0]["case_id"], "case-volume-dialog")
        self.assertEqual(case_by_variant_terms[0]["case_id"], "case-volume-dialog")
        self.assertEqual(case_by_variant_terms[0]["source_priority"], 120)
        self.assertEqual(variant_results[0]["variant_id"], "variant-mtk15-tve8402m-volume-dialog")
        self.assertEqual(patch_results[0]["patch_id"], "patch-abc")
        self.assertIn("[variant]", text)
        self.assertIn("平台/Android/项目", text)

    def test_default_search_filters_retracted_objects_left_in_lower_indexes(self):
        root = Path(tempfile.mkdtemp())
        write_jsonl(
            root / "index" / "case-index.jsonl",
            [
                {"case_id": "case-active", "title": "ActiveFeature", "status": "active"},
                {"case_id": "case-retracted", "title": "BadFeature", "status": "retracted", "retracted": True},
            ],
        )
        write_jsonl(
            root / "index" / "variant-index.jsonl",
            [
                {"variant_id": "variant-active", "case_id": "case-active", "project": "TVE8402M", "status": "validated"},
                {"variant_id": "variant-retracted", "case_id": "case-retracted", "project": "unknown", "status": "retracted"},
            ],
        )
        write_jsonl(
            root / "index" / "symbol-index.jsonl",
            [
                {"symbol_id": "symbol-active", "case_id": "case-active", "patch_id": "patch-active", "value": "GoodSymbol"},
                {"symbol_id": "symbol-retracted", "case_id": "case-retracted", "patch_id": "patch-retracted", "value": "BadSymbol"},
            ],
        )
        write_jsonl(
            root / "index" / "evidence-index.jsonl",
            [
                {"evidence_id": "evidence-active", "case_id": "case-active", "kind": "verification_result", "result": "PASS"},
                {
                    "evidence_id": "evidence-retracted",
                    "case_id": "case-retracted",
                    "kind": "verification_result",
                    "result": "RETRACTED",
                },
            ],
        )
        write_jsonl(
            root / "index" / "search-docs.jsonl",
            [{"type": "case", "case_id": "case-active", "title": "ActiveFeature", "text": "ActiveFeature GoodSymbol"}],
        )
        write_json(
            root / "patches" / "by-id" / "patch-active" / "patch.json",
            {"patch_id": "patch-active", "case_id": "case-active", "title": "Active patch", "status": "validated"},
        )
        write_json(
            root / "patches" / "by-id" / "patch-retracted" / "patch.json",
            {
                "patch_id": "patch-retracted",
                "case_id": "case-retracted",
                "title": "BadFeature patch",
                "status": "retracted",
                "retracted": True,
            },
        )

        rows = search.load_rows(root)
        row_ids = {row.get("id") for row in rows}
        text = search.format_markdown(root, "BadFeature BadSymbol", search.search(rows, "BadFeature BadSymbol", "all", 10, False), None)

        self.assertIn("case-active", row_ids)
        self.assertNotIn("case-retracted", row_ids)
        self.assertNotIn("variant-retracted", row_ids)
        self.assertNotIn("patch-retracted", row_ids)
        self.assertNotIn("symbol-retracted", row_ids)
        self.assertNotIn("evidence-retracted", row_ids)
        self.assertIn("未找到匹配结果", text)

        archive_rows = search.load_rows(root, include_archive=True)
        archive_ids = {row.get("id") for row in archive_rows}
        self.assertIn("case-retracted", archive_ids)
        self.assertIn("patch-retracted", archive_ids)

    def test_search_docs_priority_breaks_case_ties(self):
        root = Path(tempfile.mkdtemp())
        write_jsonl(
            root / "index" / "case-index.jsonl",
            [
                {"case_id": "case-low", "title": "音量弹窗位置适配", "problem": "通知音量弹窗位置不符合要求"},
                {"case_id": "case-high", "title": "音量弹窗位置适配", "problem": "通知音量弹窗位置不符合要求"},
            ],
        )
        write_jsonl(root / "index" / "variant-index.jsonl", [])
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_jsonl(root / "index" / "evidence-index.jsonl", [])
        write_jsonl(
            root / "index" / "search-docs.jsonl",
            [
                {
                    "type": "case",
                    "case_id": "case-low",
                    "title": "音量弹窗位置适配",
                    "source_priority": 30,
                    "text": "TVE8402M VolumeDialogImpl 通知音量",
                    "variant_ids": [],
                },
                {
                    "type": "case",
                    "case_id": "case-high",
                    "title": "音量弹窗位置适配",
                    "source_priority": 120,
                    "text": "TVE8402M VolumeDialogImpl 通知音量",
                    "variant_ids": [],
                },
            ],
        )

        rows = search.load_rows(root)
        results = search.search(rows, "TVE8402M VolumeDialogImpl", "case", 5, include_synthetic=False)

        self.assertEqual([item["case_id"] for item in results[:2]], ["case-high", "case-low"])

    def test_case_search_result_displays_replacement_recommendation(self):
        root = Path(tempfile.mkdtemp())
        write_jsonl(
            root / "index" / "case-index.jsonl",
            [
                {"case_id": "case-old", "title": "旧显示区域方案", "problem": "旧方案后续验证失败", "status": "obsolete"},
                {"case_id": "case-new", "title": "新显示区域方案", "problem": "已验证的新方案", "status": "active"},
            ],
        )
        write_jsonl(root / "index" / "variant-index.jsonl", [])
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_jsonl(root / "index" / "evidence-index.jsonl", [])
        write_jsonl(
            root / "index" / "search-docs.jsonl",
            [
                {
                    "type": "case",
                    "case_id": "case-old",
                    "title": "旧显示区域方案",
                    "source_priority": 10,
                    "text": "旧显示区域方案 推荐替代 case-new 新显示区域方案",
                    "variant_ids": [],
                    "replacement_case_id": "case-new",
                    "replacement_title": "新显示区域方案",
                },
                {
                    "type": "case",
                    "case_id": "case-new",
                    "title": "新显示区域方案",
                    "source_priority": 130,
                    "text": "新显示区域方案",
                    "variant_ids": [],
                    "replaces_case_ids": ["case-old"],
                },
            ],
        )

        rows = search.load_rows(root)
        old_row = next(row for row in rows if row.get("case_id") == "case-old")
        replacement_row = next(row for row in rows if row.get("case_id") == "case-new")
        text = search.format_markdown(root, "旧显示区域", [old_row, replacement_row], None)

        self.assertEqual(old_row["replacement_case_id"], "case-new")
        self.assertEqual(replacement_row["replaces_case_ids"], ["case-old"])
        self.assertIn("推荐替代: case-new / 新显示区域方案", text)
        self.assertIn("替代旧案例: case-old", text)

    def test_case_search_result_displays_knowledge_validity(self):
        root = Path(tempfile.mkdtemp())
        write_jsonl(
            root / "index" / "case-index.jsonl",
            [
                {
                    "case_id": "case-camera2",
                    "title": "Camera2 reversePortrait 方向补偿",
                    "problem": "Camera2 reversePortrait 预览方向不一致",
                    "status": "needs_review",
                    "case_confidence": "medium",
                    "knowledge_validity": {
                        "confidence": "medium",
                        "evidence_level": "static_review",
                        "risk_level": "review_required",
                        "reuse_score": 1,
                    },
                }
            ],
        )
        write_jsonl(root / "index" / "variant-index.jsonl", [])
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_jsonl(root / "index" / "evidence-index.jsonl", [])

        rows = search.load_rows(root)
        results = search.search(rows, "Camera2 reversePortrait", "case", 5, include_synthetic=False)
        text = search.format_markdown(root, "Camera2 reversePortrait", results, None)

        self.assertIn(
            "知识有效度: 可信度（confidence）=medium / 证据等级（evidence_level）=static_review / "
            "风险等级（risk_level）=review_required / 复用分（reuse_score）=1",
            text,
        )

    def test_variant_search_result_displays_knowledge_validity(self):
        root = Path(tempfile.mkdtemp())
        write_jsonl(root / "index" / "case-index.jsonl", [])
        write_jsonl(
            root / "index" / "variant-index.jsonl",
            [
                {
                    "variant_id": "variant-mtk-16-camera2",
                    "case_id": "case-camera2",
                    "implementation_scope": "Camera2 reversePortrait 方向补偿",
                    "status": "candidate",
                    "platform": "mtk",
                    "android_version": "16",
                    "project": "TVE1067M1",
                    "knowledge_validity": {
                        "confidence": "low",
                        "evidence_level": "contested",
                        "risk_level": "high",
                        "reuse_score": 0,
                    },
                }
            ],
        )
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_jsonl(root / "index" / "evidence-index.jsonl", [])

        rows = search.load_rows(root)
        results = search.search(rows, "Camera2 reversePortrait", "variant", 5, include_synthetic=False)
        text = search.format_markdown(root, "Camera2 reversePortrait", results, None)

        self.assertIn(
            "知识有效度: 可信度（confidence）=low / 证据等级（evidence_level）=contested / "
            "风险等级（risk_level）=high / 复用分（reuse_score）=0",
            text,
        )

    def test_patch_analysis_fields_are_searchable_and_formatted(self):
        root = Path(tempfile.mkdtemp())
        write_jsonl(root / "index" / "case-index.jsonl", [])
        write_jsonl(root / "index" / "variant-index.jsonl", [])
        write_jsonl(root / "index" / "symbol-index.jsonl", [])
        write_jsonl(root / "index" / "evidence-index.jsonl", [])
        write_json(
            root / "patches" / "by-id" / "patch-focus" / "patch.json",
            {
                "patch_id": "patch-focus",
                "title": "Focus fix",
                "summary": "",
                "modules": ["WindowManager"],
                "problem_summary": "Launcher launch may leave window focus stale",
                "solution_summary": "Adjust WindowManager focus update",
                "keywords": ["focus", "Launcher", "audio route/volume", "usb/device permission"],
                "inference_confidence": "medium",
                "inference_basis": ["patch modifies WindowState.java"],
                "inference_limits": ["device verification is separate"],
                "risk_areas": ["window focus", "audio route or volume behavior", "usb or device permission"],
                "modified_files": ["frameworks/base/services/core/java/com/android/server/wm/WindowState.java"],
                "patch_files": ["patches/by-id/patch-focus/patch.patch"],
                "status": "candidate",
            },
        )
        write_json(
            root / "patches" / "by-id" / "patch-policy" / "patch.json",
            {
                "patch_id": "patch-policy",
                "title": "Policy fix",
                "summary": "",
                "modules": ["Policy"],
                "problem_summary": "Behavior in Policy may need correction",
                "solution_summary": "Patch changes Policy code paths and should be reviewed against the target requirement",
                "keywords": ["Policy"],
                "inference_confidence": "low",
                "inference_basis": ["patch modifies PhoneWindowManager.java"],
                "inference_limits": ["device verification is separate"],
                "risk_areas": ["power or policy behavior"],
                "modified_files": ["frameworks/base/services/core/java/com/android/server/policy/PhoneWindowManager.java"],
                "patch_files": ["patches/by-id/patch-policy/patch.patch"],
                "status": "candidate",
            },
        )

        rows = search.load_rows(root)
        results = search.search(rows, "Launcher focus", "patch", 5, include_synthetic=False)
        text = search.format_markdown(root, "Launcher focus", results, None)

        self.assertEqual(results[0]["id"], "patch-focus")
        self.assertIn("补丁问题线索", text)
        self.assertIn("window focus", text)
        self.assertIn("音频路由/音量", text)
        self.assertIn("USB/设备权限", text)

        policy_results = search.search(rows, "Policy", "patch", 5, include_synthetic=False)
        policy_text = search.format_markdown(root, "Policy", policy_results, None)

        self.assertIn("Policy 相关行为需要核对和修正", policy_text)
        self.assertIn("补丁修改了 Policy 相关代码路径", policy_text)
        self.assertIn("按键/电源/策略行为", policy_text)

    def test_merge_confirmation_list_uses_member_api(self):
        payload = {
            "total": 1,
            "items": [
                {
                    "review_id": "review-pending-merge",
                    "package_key": "20260703/wick/pending-patch",
                    "material_display_title": "副屏 RecentView 入口调整",
                    "confirmation_status": "pending_merge_confirmation",
                    "confirmation_status_label": "等待成员确认合并",
                    "target_knowledge": {
                        "case_id": "case-hdmi-recentview",
                        "title": "HDMI 副屏 RecentView",
                    },
                    "actions": {"can_submit_dispute": True},
                }
            ],
        }
        seen = {}

        def fake_urlopen(request, timeout=0):
            seen["url"] = request.full_url
            seen["method"] = request.get_method()
            seen["user"] = request.get_header("X-akbs-user")
            return FakeHttpResponse(payload)

        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(Path(tempfile.mkdtemp()) / "codex-home"),
                "CODEX_REPORT_AKBS_ENDPOINT_API_BASE_URL": "http://akbs.invalid",
                "CODEX_REPORT_PROFILE": "member01",
            },
        ):
            stdout = io.StringIO()
            with patch("urllib.request.urlopen", fake_urlopen), patch("sys.stdout", new=stdout):
                code = search.main(["--merge-confirmation", "list"])

        self.assertEqual(code, 0)
        self.assertEqual(seen["url"], "http://akbs.invalid/akbs/api/member/me/merge-confirmations")
        self.assertEqual(seen["method"], "GET")
        self.assertEqual(seen["user"], "unknown")
        self.assertIn("副屏 RecentView 入口调整", stdout.getvalue())
        self.assertIn("case-hdmi-recentview", stdout.getvalue())

    def test_merge_confirmation_analyze_reads_detail_target_compare_without_dispute(self):
        responses = {
            "http://akbs.invalid/akbs/api/member/me/merge-confirmations/review-pending-merge": {
                "review_id": "review-pending-merge",
                "package_key": "20260703/wick/pending-patch",
                "material_display_title": "副屏 RecentView 入口调整",
                "confirmation_status": "pending_merge_confirmation",
                "target_knowledge": {"case_id": "case-hdmi", "title": "HDMI 副屏知识"},
                "actions": {"can_submit_dispute": True},
                "member_agent_context": {
                    "schema": "akbs-merge-confirmation-agent-context-v1",
                    "reuse_grade": "merge_candidate",
                },
            },
            "http://akbs.invalid/akbs/api/member/me/merge-confirmations/review-pending-merge/target": {
                "review_id": "review-pending-merge",
                "target_knowledge": {"case_id": "case-hdmi", "title": "HDMI 副屏知识", "summary": "目标知识摘要"},
            },
            "http://akbs.invalid/akbs/api/member/me/merge-confirmations/review-pending-merge/compare": {
                "review_id": "review-pending-merge",
                "source_material": {"title": "副屏 RecentView 入口调整", "package_key": "20260703/wick/pending-patch"},
                "target_knowledge": {"case_id": "case-hdmi", "title": "HDMI 副屏知识"},
                "merge_basis": [{"summary": "代码锚点同为 RecentView"}],
                "matched_anchors": ["RecentView", "DisplayPolicy"],
                "counter_evidence": [{"summary": "目标知识未覆盖副屏入口差异"}],
                "member_agent_context": {
                    "schema": "akbs-merge-confirmation-agent-context-v1",
                    "reuse_grade": "merge_candidate",
                },
            },
        }
        requests = []

        def fake_urlopen(request, timeout=0):
            requests.append((request.get_method(), request.full_url))
            return FakeHttpResponse(responses[request.full_url])

        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(Path(tempfile.mkdtemp()) / "codex-home"),
                "CODEX_REPORT_AKBS_ENDPOINT_API_BASE_URL": "http://akbs.invalid",
            },
        ):
            stdout = io.StringIO()
            with patch("urllib.request.urlopen", fake_urlopen), patch("sys.stdout", new=stdout):
                code = search.main(["--merge-confirmation", "analyze", "--merge-confirmation-id", "review-pending-merge"])

        self.assertEqual(code, 0)
        self.assertEqual([method for method, _url in requests], ["GET", "GET", "GET"])
        text = stdout.getvalue()
        self.assertIn("合并确认 Codex 分析摘要", text)
        self.assertIn("人看摘要", text)
        self.assertIn("Codex 分析证据", text)
        self.assertIn("代码锚点同为 RecentView", text)
        self.assertIn("目标知识未覆盖副屏入口差异", text)
        self.assertIn("异议理由草稿", text)

    def test_merge_confirmation_api_failure_does_not_fabricate_basis(self):
        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(Path(tempfile.mkdtemp()) / "codex-home"),
                "CODEX_REPORT_AKBS_ENDPOINT_API_BASE_URL": "http://akbs.invalid",
            },
        ):
            with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
                with self.assertRaises(SystemExit) as raised:
                    search.main(["--merge-confirmation", "detail", "--merge-confirmation-id", "review-missing"])

        self.assertIn("merge confirmation API unavailable", str(raised.exception))
        self.assertIn("offline", str(raised.exception))

    def test_merge_confirmation_dispute_requires_explicit_send_flag(self):
        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(Path(tempfile.mkdtemp()) / "codex-home"),
                "CODEX_REPORT_AKBS_ENDPOINT_API_BASE_URL": "http://akbs.invalid",
            },
        ):
            with patch("urllib.request.urlopen") as urlopen:
                with self.assertRaises(SystemExit) as raised:
                    search.main(
                        [
                            "--merge-confirmation",
                            "dispute",
                            "--merge-confirmation-id",
                            "review-pending-merge",
                            "--dispute-reason",
                            "目标知识不一致",
                        ]
                    )

        urlopen.assert_not_called()
        self.assertIn("--send-dispute", str(raised.exception))

    def test_merge_confirmation_dispute_posts_only_with_send_flag(self):
        seen = {}

        def fake_urlopen(request, timeout=0):
            seen["url"] = request.full_url
            seen["method"] = request.get_method()
            seen["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHttpResponse({"dispute_id": "merge-dispute-abc", "state": "dispute_open"})

        with patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(Path(tempfile.mkdtemp()) / "codex-home"),
                "CODEX_REPORT_AKBS_ENDPOINT_API_BASE_URL": "http://akbs.invalid",
            },
        ):
            stdout = io.StringIO()
            with patch("urllib.request.urlopen", fake_urlopen), patch("sys.stdout", new=stdout):
                code = search.main(
                    [
                        "--merge-confirmation",
                        "dispute",
                        "--merge-confirmation-id",
                        "review-pending-merge",
                        "--send-dispute",
                        "--dispute-reason",
                        "目标知识不一致",
                        "--member-assessment",
                        "建议新建知识",
                        "--evidence-ref",
                        "compare.counter_evidence[0]",
                    ]
                )

        self.assertEqual(code, 0)
        self.assertEqual(seen["url"], "http://akbs.invalid/akbs/api/member/me/merge-confirmations/review-pending-merge/dispute")
        self.assertEqual(seen["method"], "POST")
        self.assertEqual(seen["body"]["reason"], "目标知识不一致")
        self.assertEqual(seen["body"]["member_assessment"], "建议新建知识")
        self.assertEqual(seen["body"]["evidence_refs"], ["compare.counter_evidence[0]"])
        self.assertIn("merge-dispute-abc", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
