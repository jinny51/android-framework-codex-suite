#!/usr/bin/env python3
"""Infer Android module profiles from files in the canonical remote workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re


def safe_relative(value: str, *, field: str) -> PurePosixPath:
    path = PurePosixPath(value or ".")
    if path.is_absolute() or ".." in path.parts or any(ord(ch) < 32 for ch in value):
        raise SystemExit(f"{field} must be a safe project-relative POSIX path")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Infer a remote Android build profile.")
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--working-subpath", default=".")
    parser.add_argument("--path", action="append", required=True)
    parser.add_argument("--profile", default="")
    return parser.parse_args()


def nearest_build_files(root: Path, relative: PurePosixPath):
    current = root.joinpath(*relative.parts)
    if current.is_file():
        current = current.parent
    if not current.exists():
        current = current.parent
    while True:
        try:
            current.relative_to(root)
        except ValueError:
            return
        for name in ("Android.bp", "Android.mk"):
            candidate = current / name
            if candidate.is_file():
                yield candidate
        if current == root:
            return
        current = current.parent


def parse_android_bp(path: Path, root: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    result = []
    pattern = re.compile(
        r"(?s)(android_app|android_test|java_library|java_library_static|android_library|"
        r"cc_binary|prebuilt_etc|apex)\s*\{(.*?)\n\}"
    )
    for match in pattern.finditer(text):
        block_type, body = match.groups()
        name = re.search(r'\bname\s*:\s*"([^"]+)"', body)
        if not name:
            continue
        module = name.group(1)
        artifact = f"{module}.apk" if block_type in {"android_app", "android_test"} else ""
        if module == "services":
            artifact = "services.jar"
        elif module == "framework-minus-apex":
            artifact = "framework.jar"
        result.append((module, artifact, f"{path.relative_to(root).as_posix()}:{block_type}"))
    return result


def parse_android_mk(path: Path, root: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    result = []
    for variable in ("LOCAL_PACKAGE_NAME", "LOCAL_MODULE"):
        pattern = rf"(?m)^\s*{variable}\s*:?=\s*([A-Za-z0-9_.+-]+)"
        for module in re.findall(pattern, text):
            artifact = f"{module}.apk" if variable == "LOCAL_PACKAGE_NAME" else ""
            result.append((module, artifact, f"{path.relative_to(root).as_posix()}:{variable}"))
    return result


def parsed_modules(root: Path, relative: PurePosixPath):
    for build_file in nearest_build_files(root, relative):
        values = (
            parse_android_bp(build_file, root)
            if build_file.name == "Android.bp"
            else parse_android_mk(build_file, root)
        )
        if values:
            return values
    return []


RULES = (
    (lambda p: p.startswith("frameworks/base/services/"), "framework-services", "services", "services.jar"),
    (lambda p: p.startswith("frameworks/base/core/res/"), "framework-res", "framework-res", "framework-res.apk"),
    (
        lambda p: p.startswith(("frameworks/base/core/", "frameworks/base/graphics/", "frameworks/base/media/")),
        "framework",
        "framework-minus-apex",
        "framework.jar",
    ),
    (lambda p: "packages/SystemUI/" in p, "systemui", "SystemUI", "SystemUI.apk"),
    (lambda p: "packages/apps/Launcher3/" in p, "launcher3", "Launcher3", "Launcher3.apk"),
    (lambda p: "packages/apps/Settings/" in p, "settings", "Settings", "Settings.apk"),
    (lambda p: p.startswith("bootable/") or (p.startswith("device/") and "boot" in p.lower()), "bootimage", "bootimage", "boot.img"),
)


def main() -> int:
    args = parse_args()
    root = args.project_root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise SystemExit("project root is not a directory")
    working = safe_relative(args.working_subpath, field="working-subpath")

    paths: list[PurePosixPath] = []
    for raw in args.path:
        provided = safe_relative(raw, field="path")
        combined = provided if working == PurePosixPath(".") else working / provided
        paths.append(combined)

    items: list[tuple[str, str, str]] = []
    reasons: list[str] = []
    for relative in paths:
        value = relative.as_posix()
        matched = False
        for predicate, profile, module, artifact in RULES:
            if predicate(value):
                items.append((profile, module, artifact))
                reasons.append(f"{value}:path-rule")
                matched = True
                break
        if matched:
            continue
        for module, artifact, source in parsed_modules(root, relative)[:2]:
            profile = re.sub(r"[^a-z0-9]+", "-", module.lower()).strip("-") or "custom"
            items.append((profile, module, artifact))
            reasons.append(f"{value}:{source}")

    modules = list(dict.fromkeys(module for _, module, _ in items if module))
    artifacts = list(dict.fromkeys(artifact for _, _, artifact in items if artifact))
    profiles = list(dict.fromkeys(profile for profile, _, _ in items if profile))
    if args.profile:
        profile = args.profile
    elif len(profiles) == 1:
        profile = profiles[0]
    elif "framework-services" in profiles:
        profile = "framework-services"
    elif "systemui" in profiles:
        profile = "systemui"
    elif profiles:
        profile = f"mixed-{profiles[0]}"
    else:
        profile = "custom"
    payload = {
        "profile": profile,
        "modules": modules,
        "artifact_names": artifacts,
        "confidence": "high" if len(modules) == 1 else ("medium" if modules else "low"),
        "working_subpath": working.as_posix(),
        "paths": [path.as_posix() for path in paths],
        "reasons": reasons[:8],
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
