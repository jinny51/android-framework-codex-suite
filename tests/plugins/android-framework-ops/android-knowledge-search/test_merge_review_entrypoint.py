from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = (
    REPO_ROOT
    / "plugins/android-framework-ops/skills/android-knowledge-merge-review/"
    "scripts/android_knowledge_merge_review.py"
)


def load_entrypoint():
    spec = importlib.util.spec_from_file_location("android_knowledge_merge_review", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_merge_review_entrypoint_maps_read_only_analysis() -> None:
    module = load_entrypoint()
    with patch.object(module, "legacy_merge_main", return_value=0) as legacy:
        result = module.main(
            ["analyze", "--confirmation-id", "merge-confirmation-1", "--json"]
        )
    assert result == 0
    legacy.assert_called_once_with(
        [
            "--merge-confirmation",
            "analyze",
            "--merge-confirmation-id",
            "merge-confirmation-1",
            "--server-timeout",
            "3.0",
            "--json",
        ]
    )


def test_merge_review_entrypoint_preserves_explicit_dispute_flags() -> None:
    module = load_entrypoint()
    with patch.object(module, "legacy_merge_main", return_value=0) as legacy:
        result = module.main(
            [
                "dispute",
                "--confirmation-id",
                "merge-confirmation-1",
                "--send-dispute",
                "--dispute-reason",
                "目标知识不一致",
                "--evidence-ref",
                "compare.counter_evidence[0]",
            ]
        )
    assert result == 0
    arguments = legacy.call_args.args[0]
    assert "--send-dispute" in arguments
    assert arguments[arguments.index("--dispute-reason") + 1] == "目标知识不一致"
    assert arguments[arguments.index("--evidence-ref") + 1] == "compare.counter_evidence[0]"
