#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
PATCH_NAME_RE = re.compile(r"^[a-z0-9]+[0-9]+-[A-Za-z0-9._-]+@[a-z0-9_.-]+\.patch$")
PLATFORM_RE = re.compile(r"^[a-z0-9]+[0-9]+$")
AUTHOR_DATE_RE = re.compile(r"//[A-Za-z0-9_]+\s+\d{8}@")
BANNED_LOG_PATTERNS = ("Log.d(", "Log.i(", "Log.w(", "Slog.d(", "Slog.i(", "Slog.w(")


def run(cmd: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        errors="replace",
    )
    if check and cp.returncode != 0:
        raise SystemExit(cp.stderr.strip() or cp.stdout.strip() or f"command failed: {' '.join(cmd)}")
    return cp


def git_root(path: Path) -> Path:
    cp = run(["git", "rev-parse", "--show-toplevel"], path)
    if cp.returncode != 0:
        raise SystemExit("当前目录不是 git 仓库，无法生成补丁。")
    return Path(cp.stdout.strip()).resolve()


def slug(value: str, *, lower: bool = True) -> str:
    value = value.strip()
    if lower:
        value = value.lower()
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-._")
    return value or "unnamed"


def changed_files_from_diff(diff_text: str) -> list[str]:
    files: list[str] = []
    for match in re.finditer(r"^diff --git a/(.+?) b/(.+)$", diff_text, re.M):
        old, new = match.group(1), match.group(2)
        path = new if new != "/dev/null" else old
        if path not in files:
            files.append(path)
    return files


def infer_module(files: list[str]) -> str:
    if not files:
        return "frameworks-base"
    first = files[0]
    rules = [
        ("frameworks/base/", "frameworks-base"),
        ("frameworks/native/", "frameworks-native"),
        ("packages/SystemUI/", "systemui"),
        ("packages/apps/Launcher", "launcher"),
        ("packages/apps/Settings/", "settings"),
        ("system/core/", "system-core"),
        ("frameworks/av/", "frameworks-av"),
    ]
    for prefix, module in rules:
        if first.startswith(prefix):
            return module
    parts = first.split("/")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return parts[0]


def added_lines(diff_text: str) -> list[str]:
    return [line[1:] for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++")]


def facts_from_diff(diff_text: str) -> dict[str, Any]:
    files = changed_files_from_diff(diff_text)
    added = "\n".join(added_lines(diff_text))
    all_text = diff_text
    return {
        "modified_files": files,
        "system_properties": sorted(set(re.findall(r"\b(?:persist|ro|sys|debug|vendor)\.[A-Za-z0-9_.-]+", all_text))),
        "settings_keys": sorted(set(re.findall(r"Settings\.(?:System|Secure|Global)\.([A-Za-z0-9_.-]+)", all_text))),
        "resource_keys": sorted(set([*re.findall(r"R\.string\.([A-Za-z0-9_]+)", all_text), *re.findall(r"@string/([A-Za-z0-9_]+)", all_text)])),
        "framework_log_keys": sorted(set(re.findall(r"FrameworkLog\.([A-Za-z0-9_]+)", all_text))),
        "banned_log_hits": sorted(pattern for pattern in BANNED_LOG_PATTERNS if pattern in added),
        "author_date_marker_present": bool(AUTHOR_DATE_RE.search(all_text)),
    }


def git_metadata(root: Path) -> dict[str, str]:
    def output(args: list[str]) -> str:
        cp = run(["git", *args], root)
        return cp.stdout.strip() if cp.returncode == 0 else ""

    return {
        "root": str(root),
        "branch": output(["branch", "--show-current"]),
        "head": output(["rev-parse", "--short", "HEAD"]),
        "status": output(["status", "--short"]),
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def bullet_list(items: list[str]) -> str:
    if not items:
        return "无"
    return "\n".join(f"- `{item}`" for item in items)


def plain_bullets(items: list[str]) -> str:
    if not items:
        return "待补充"
    return "\n".join(f"- {item}" for item in items)


def inferred_verification_method(args: argparse.Namespace) -> str:
    if args.verification_method:
        return args.verification_method
    if args.equivalent_type or args.equivalent_reason or args.equivalent_coverage or args.remaining_risk:
        return "equivalent"
    if args.device or args.device_verification:
        return "device"
    return "not_provided"


def verification_result(args: argparse.Namespace) -> dict[str, Any]:
    method = inferred_verification_method(args)
    has_evidence = bool(
        args.verification
        or args.device_verification
        or args.equivalent_coverage
        or args.equivalent_reason
        or args.health_check
        or args.artifact
    )
    result = args.verification_result or ("PASS" if has_evidence else "INFO")
    payload: dict[str, Any] = {
        "result": result,
        "method": method,
        "build": args.verification or [],
        "device": args.device or "",
        "steps": args.device_verification or [],
        "observed": "\n".join(args.device_verification or []),
        "health_checks": args.health_check or [],
        "artifacts": args.artifact or [],
    }
    if method == "equivalent":
        payload.update(
            {
                "equivalent_type": args.equivalent_type or "",
                "reason": args.equivalent_reason or "",
                "coverage": args.equivalent_coverage or [],
                "remaining_risk": args.remaining_risk or "",
            }
        )
    return payload


def search_before_change(args: argparse.Namespace) -> dict[str, Any]:
    queries = args.search_query or []
    results = args.search_result or []
    summary = args.search_summary or ""
    return {
        "result": "INFO",
        "method": "knowledge_search",
        "searched": bool(queries or results or summary),
        "queries": queries,
        "results": results,
        "summary": summary or "not provided by capture command",
    }


def validate_verification_for_status(args: argparse.Namespace, payload: dict[str, Any]) -> list[str]:
    if args.status not in {"validated", "released"}:
        return []

    errors: list[str] = []
    method = payload.get("method")
    if payload.get("result") != "PASS":
        errors.append("status 是 validated/released 时 verification-result.result 必须是 PASS")

    if method == "device":
        if not args.verification:
            errors.append("status 是 validated/released 且 method=device 时必须提供 --verification 构建验证")
        if not args.device_verification:
            errors.append("status 是 validated/released 且 method=device 时必须提供 --device-verification 真机验证")
    elif method == "equivalent":
        if not args.equivalent_type:
            errors.append("status 是 validated/released 且 method=equivalent 时必须提供 --equivalent-type")
        if not args.equivalent_reason:
            errors.append("status 是 validated/released 且 method=equivalent 时必须提供 --equivalent-reason")
        if not args.equivalent_coverage:
            errors.append("status 是 validated/released 且 method=equivalent 时必须提供 --equivalent-coverage")
        if not args.remaining_risk:
            errors.append("status 是 validated/released 且 method=equivalent 时必须提供 --remaining-risk")
    else:
        errors.append("status 是 validated/released 时必须提供 device 或 equivalent 验证证据")

    return errors


def readme_text(
    patch_name: str,
    args: argparse.Namespace,
    facts: dict[str, Any],
    package_check: dict[str, Any],
) -> str:
    verification = args.verification or []
    risk = args.risk or "待结合当前项目、触发路径和验证结果补充。"
    rollback = args.rollback or "在目标源码树执行 `git apply -R <patch>`，或回退对应提交。"
    log_control = "无直接 Log.d/i/w 或 Slog.d/i/w 新增。"
    if facts["banned_log_hits"]:
        log_control = "检测到直接日志调用，提交知识库前必须改为 FrameworkLog 或说明保留原因：" + ", ".join(facts["banned_log_hits"])

    return f"""# {patch_name}

## 功能描述

{args.summary}

## 修改点

{bullet_list(facts["modified_files"])}

## 影响范围

- 项目: {args.project}
- 模块: {args.module}
- 状态: {args.status}

## 关键符号

### SystemProperties

{bullet_list(facts["system_properties"])}

### Settings Key

{bullet_list(facts["settings_keys"])}

### FrameworkLog Key

{bullet_list(facts["framework_log_keys"])}

### 字符串资源

{bullet_list(facts["resource_keys"])}

## 日志控制

{log_control}

## SystemProperties

{bullet_list(facts["system_properties"])}

## 字符串国际化

{bullet_list(facts["resource_keys"])}

## 构建验证

{plain_bullets(verification)}

## 设备验证

{plain_bullets(args.device_verification or [])}

## 开发前知识库检索

### 检索词

{plain_bullets(args.search_query or [])}

### 检索结果

{plain_bullets(args.search_result or [])}

## 风险说明

{risk}

## 可回滚性

{rollback}

## 打包检查

- author_date_marker_present: {str(facts["author_date_marker_present"]).lower()}
- package_check: {package_check["status"]}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package Android Framework git changes into patch/readme/evidence assets.")
    parser.add_argument("--source-root", default=".", help="Android source git repository. Default: current directory.")
    parser.add_argument("--out-dir", default=".codex/patch-packages", help="Output root. Default: .codex/patch-packages")
    parser.add_argument("--run-id", help="Output package id. Default: YYYYMMDD-HHMMSS-patch")
    parser.add_argument("--platform", required=True, help="Platform plus Android version token, for example rk14, mtk14, unisoc13.")
    parser.add_argument("--module", help="Patch module name. Default inferred from changed files.")
    parser.add_argument("--feature", required=True, help="Feature slug for filename, for example allow-powerkey-to-user.")
    parser.add_argument("--summary", required=True, help="Human-readable requirement or patch summary.")
    parser.add_argument("--project", default="Android Framework", help="Project name for manifest/readme.")
    parser.add_argument("--status", choices=["draft", "candidate", "validated", "released", "buggy"], default="draft")
    parser.add_argument("--verification", action="append", default=[], help="Build verification fact. Repeatable.")
    parser.add_argument("--verification-result", choices=["PASS", "FAIL", "WARN", "INFO", "SKIPPED"], help="Overall verification result. Default: PASS when evidence is present, otherwise INFO.")
    parser.add_argument("--verification-method", choices=["device", "equivalent", "not_provided"], help="Verification method. Default inferred from verification arguments.")
    parser.add_argument("--device", default="", help="Device or board used for device verification.")
    parser.add_argument("--device-verification", action="append", default=[], help="Device verification fact. Repeatable.")
    parser.add_argument("--health-check", action="append", default=[], help="Health check evidence, such as boot, logcat, or dumpsys checks. Repeatable.")
    parser.add_argument("--artifact", action="append", default=[], help="Build or verification artifact path/reference. Repeatable.")
    parser.add_argument("--equivalent-type", default="", help="Equivalent verification type, for example artifact_static_check.")
    parser.add_argument("--equivalent-reason", default="", help="Why equivalent verification is acceptable.")
    parser.add_argument("--equivalent-coverage", action="append", default=[], help="Equivalent verification coverage item. Repeatable.")
    parser.add_argument("--remaining-risk", default="", help="Remaining risk after equivalent verification.")
    parser.add_argument("--search-query", action="append", default=[], help="Knowledge-base query performed before development. Repeatable.")
    parser.add_argument("--search-result", action="append", default=[], help="Search result or reuse decision from the pre-change search. Repeatable.")
    parser.add_argument("--search-summary", default="", help="Short summary of pre-change knowledge search.")
    parser.add_argument("--risk", default="", help="Risk note for readme.")
    parser.add_argument("--rollback", default="", help="Rollback note for readme.")
    parser.add_argument("--allow-missing-author-date", action="store_true", help="Allow package even when patch lacks //name YYYYMMDD@ marker.")
    parser.add_argument("--allow-banned-logs", action="store_true", help="Allow package even when added lines contain direct Log/Slog calls.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = git_root(Path(args.source_root).resolve())
    if not PLATFORM_RE.fullmatch(slug(args.platform)):
        raise SystemExit("--platform 必须包含平台和 Android 版本，例如 rk14、mtk14、unisoc13。")

    diff_cp = run(["git", "diff", "--binary", "--full-index", "HEAD", "--"], source_root, check=True)
    diff_text = diff_cp.stdout
    if not diff_text.strip():
        raise SystemExit("没有发现相对 HEAD 的 git diff，无法生成 patch。")

    facts = facts_from_diff(diff_text)
    git_info = git_metadata(source_root)
    args.module = slug(args.module or infer_module(facts["modified_files"]))
    platform = slug(args.platform)
    feature = slug(args.feature)
    patch_name = f"{platform}-{args.module}@{feature}.patch"
    if not PATCH_NAME_RE.fullmatch(patch_name):
        raise SystemExit(f"生成的 patch 文件名不符合规范: {patch_name}")

    now = dt.datetime.now()
    run_id = args.run_id or f"{now:%Y%m%d-%H%M%S}-patch"
    package_dir = (source_root / args.out_dir / run_id).resolve()
    if package_dir.exists():
        raise SystemExit(f"输出目录已存在: {package_dir}")

    patch_dir = package_dir / "patches"
    evidence_dir = package_dir / "evidence"
    patch_dir.mkdir(parents=True)
    evidence_dir.mkdir(parents=True)

    patch_path = patch_dir / patch_name
    readme_path = patch_dir / f"{patch_path.stem}.readme.md"
    patch_path.write_text(diff_text, encoding="utf-8")

    errors: list[str] = []
    warnings: list[str] = []
    if not facts["author_date_marker_present"] and not args.allow_missing_author_date:
        errors.append("patch 缺少作者日期备注，例如 //gyf 20251016@")
    if facts["banned_log_hits"] and not args.allow_banned_logs:
        errors.append("patch 新增代码包含直接 Log/Slog 调用，应改用 FrameworkLog: " + ", ".join(facts["banned_log_hits"]))
    verification_payload = verification_result(args)
    search_payload = search_before_change(args)
    errors.extend(validate_verification_for_status(args, verification_payload))

    package_check = {"status": "FAIL" if errors else "PASS", "errors": errors, "warnings": warnings}
    readme_path.write_text(readme_text(patch_name, args, facts, package_check), encoding="utf-8")
    evidence_items = [
        {
            "id": "changed-files",
            "kind": "changed_files",
            "path": "evidence/changed-files.json",
            "result": "INFO",
            "summary": "changed files and extracted patch facts",
        },
        {
            "id": "verification-result",
            "kind": "verification_result",
            "path": "evidence/verification-result.json",
            "result": verification_payload["result"],
            "summary": f"{verification_payload['method']} verification evidence",
        },
        {
            "id": "search-before-change",
            "kind": "search_before_change",
            "path": "evidence/search-before-change.json",
            "result": "INFO",
            "summary": "knowledge search performed before development",
        },
        {
            "id": "package-check",
            "kind": "package_check",
            "path": "evidence/package-check.json",
            "result": package_check["status"],
            "summary": "local patch package checks",
        },
    ]

    patch_item = {
        "path": f"patches/{patch_path.name}",
        "readme": f"patches/{readme_path.name}",
        "status": args.status,
        "project": args.project,
        "facts": facts,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_type": "framework_patch",
        "project": args.project,
        "summary": args.summary,
        "status": args.status,
        "created_at": now.isoformat(timespec="seconds"),
        "source_root": str(source_root),
        "git": git_info,
        "patches": [patch_item],
        "evidence": evidence_items,
    }
    write_json(package_dir / "manifest.json", manifest)
    write_json(evidence_dir / "changed-files.json", {"facts": facts, "git": manifest["git"]})
    write_json(evidence_dir / "verification-result.json", verification_payload)
    write_json(evidence_dir / "search-before-change.json", search_payload)
    write_json(evidence_dir / "package-check.json", package_check)

    result = {
        "package": str(package_dir),
        "patch": str(patch_path),
        "readme": str(readme_path),
        "local_check": package_check,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
