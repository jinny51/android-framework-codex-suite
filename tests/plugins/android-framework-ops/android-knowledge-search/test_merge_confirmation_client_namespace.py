from __future__ import annotations

import importlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPO_ROOT / "plugins/android-framework-ops"
PLUGIN_LIB = PLUGIN_ROOT / "lib"
SEARCH_SCRIPTS = PLUGIN_ROOT / "skills/android-knowledge-search/scripts"

for path in (PLUGIN_LIB, SEARCH_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def test_legacy_search_api_exports_canonical_merge_client() -> None:
    legacy = importlib.import_module("knowledge_search.api")
    client = importlib.import_module(
        "android_engineering_ops.knowledge.merge_confirmation.client"
    )
    member = importlib.import_module("android_engineering_ops.knowledge.member")

    assert legacy.require_member_alias is member.require_member_alias
    assert legacy.fetch_merge_confirmation_payload is client.fetch_merge_confirmation_payload
    assert legacy.post_merge_dispute is client.post_merge_dispute
    assert legacy.merge_api_error is client.merge_api_error
    assert legacy.member_request_headers is client.member_request_headers
