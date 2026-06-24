from __future__ import annotations

import re


DAILY_BUNDLE_SUMMARY_RE = re.compile(
    r"(?:今日|本日|当天)补丁|补丁合集|(?:今日|本日|当天).*?(?:\d+\s*(?:个|项|份)|多个|若干).*?补丁"
)
MULTI_FEATURE_COLLECTION_RE = re.compile(
    r"(?:多功能混包|多个独立(?:功能|需求|补丁)|多个(?:功能|需求|补丁).*?(?:合集|汇总|整理)|"
    r"[两二三四五六七八九十]\s*项功能|\d+\s*项功能|\d+\s*个独立(?:功能|需求|补丁))"
)
LISTED_FEATURE_PACKAGE_RE = re.compile(r"[^，。；\n]+、[^，。；\n]+(?:，)?(?:以及|和)[^，。；\n]+补丁包")


def aggregate_package_scope_errors(text: str, patch_count: int = 0) -> list[str]:
    if not (
        DAILY_BUNDLE_SUMMARY_RE.search(text)
        or MULTI_FEATURE_COLLECTION_RE.search(text)
        or LISTED_FEATURE_PACKAGE_RE.search(text)
    ):
        return []
    count = f"当前约 {patch_count} 个补丁。" if patch_count else ""
    return [
        f"补丁包（patch package）不能是无共同目标的聚合包（aggregate package）。{count}"
        "请用补丁采集技能（android-framework-patch-capture）按功能拆分（function split）为多个普通补丁包；"
        "一个补丁包只能对应一个功能。"
    ]
