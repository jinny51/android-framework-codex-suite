#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
infer-profile.sh --repo PATH --path FILE [--path FILE ...] [options]

Infer a project-local build profile from Android source paths.

Required:
  --repo PATH          Local WSL/Samba repo path.
  --path FILE          Changed or requirement-relevant path. Repeatable.

Optional:
  --profile NAME       Override suggested profile name.
  --from-file FILE     Read newline-separated paths. Use - for stdin.

Output:
  Shell-style KEY=VALUE lines:
    PROFILE, MODULES, ARTIFACTS, CONFIDENCE, REASON

The script only reads local source files. It does not run git or builds.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

REPO=""
PROFILE_OVERRIDE=""
FROM_FILE=""
PATHS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --path) PATHS+=("${2:-}"); shift 2 ;;
    --profile) PROFILE_OVERRIDE="${2:-}"; shift 2 ;;
    --from-file) FROM_FILE="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -n "$REPO" ]] || die "--repo is required"
[[ -d "$REPO" ]] || die "repo path does not exist: $REPO"

if [[ -n "$FROM_FILE" ]]; then
  if [[ "$FROM_FILE" == "-" ]]; then
    while IFS= read -r path; do
      [[ -n "$path" ]] && PATHS+=("$path")
    done
  else
    [[ -f "$FROM_FILE" ]] || die "path list not found: $FROM_FILE"
    while IFS= read -r path; do
      [[ -n "$path" ]] && PATHS+=("$path")
    done <"$FROM_FILE"
  fi
fi

((${#PATHS[@]} > 0)) || die "at least one --path or --from-file entry is required"

python3 - "$REPO" "$PROFILE_OVERRIDE" "${PATHS[@]}" <<'PY'
import os
import re
import shlex
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
profile_override = sys.argv[2]
raw_paths = sys.argv[3:]

def q(value):
    return shlex.quote(value)

def relpath(raw):
    p = Path(raw)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(repo).as_posix()
        except Exception:
            return p.as_posix().lstrip("/")
    return p.as_posix().lstrip("./")

paths = [relpath(p) for p in raw_paths if p]

def nearest_build_files(path):
    cur = repo / path
    if cur.is_file():
        cur = cur.parent
    if not cur.exists():
        cur = (repo / path).parent
    while True:
        for name in ("Android.bp", "Android.mk"):
            candidate = cur / name
            if candidate.is_file():
                yield candidate
        if cur == repo or cur.parent == cur:
            break
        cur = cur.parent

def parse_android_bp(path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    modules = []
    for block_match in re.finditer(r"(?s)(android_app|android_test|java_library|java_library_static|android_library|cc_binary|prebuilt_etc|apex)\s*\{(.*?)\n\}", text):
        block_type, body = block_match.group(1), block_match.group(2)
        name_match = re.search(r'\bname\s*:\s*"([^"]+)"', body)
        if not name_match:
            continue
        name = name_match.group(1)
        artifact = ""
        if block_type in {"android_app", "android_test"}:
            artifact = f"{name}.apk"
        elif name in {"services", "framework-minus-apex"}:
            artifact = "services.jar" if name == "services" else "framework.jar"
        modules.append((name, artifact, f"{path.relative_to(repo).as_posix()}:{block_type}"))
    return modules

def parse_android_mk(path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    modules = []
    for var in ("LOCAL_PACKAGE_NAME", "LOCAL_MODULE"):
        for name in re.findall(rf"(?m)^\s*{var}\s*:?=\s*([A-Za-z0-9_.+-]+)", text):
            artifact = f"{name}.apk" if var == "LOCAL_PACKAGE_NAME" else ""
            modules.append((name, artifact, f"{path.relative_to(repo).as_posix()}:{var}"))
    return modules

def parsed_modules_for(path):
    seen = set()
    result = []
    for build_file in nearest_build_files(path):
        modules = parse_android_bp(build_file) if build_file.name == "Android.bp" else parse_android_mk(build_file)
        for item in modules:
            if item[0] not in seen:
                seen.add(item[0])
                result.append(item)
        if result:
            break
    return result

rules = [
    (lambda p: p.startswith("frameworks/base/services/"), ("framework-services", "services", "services.jar", "framework services path")),
    (lambda p: p.startswith("frameworks/base/core/res/"), ("framework-res", "framework-res", "framework-res.apk", "framework resources path")),
    (lambda p: p.startswith("frameworks/base/core/") or p.startswith("frameworks/base/graphics/") or p.startswith("frameworks/base/media/"), ("framework", "framework-minus-apex", "framework.jar", "framework jar path")),
    (lambda p: "packages/SystemUI/" in p or p.startswith("frameworks/base/packages/SystemUI/"), ("systemui", "SystemUI", "SystemUI.apk", "SystemUI path")),
    (lambda p: "packages/apps/Launcher3/" in p or p.startswith("packages/apps/Launcher3/"), ("launcher3", "Launcher3", "Launcher3.apk", "Launcher3 path")),
    (lambda p: "packages/apps/Settings/" in p or p.startswith("packages/apps/Settings/"), ("settings", "Settings", "Settings.apk", "Settings path")),
    (lambda p: p.startswith("bootable/") or p.startswith("device/") and "boot" in p.lower(), ("bootimage", "bootimage", "boot.img", "boot image path")),
]

module_items = []
reasons = []

for path in paths:
    matched = False
    for pred, values in rules:
        if pred(path):
            profile, module, artifact, reason = values
            module_items.append((profile, module, artifact))
            reasons.append(f"{path}:{reason}")
            matched = True
            break
    if matched:
        continue
    parsed = parsed_modules_for(path)
    if parsed:
        for name, artifact, source in parsed[:2]:
            profile = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "custom"
            module_items.append((profile, name, artifact))
            reasons.append(f"{path}:{source}")

seen_modules = []
seen_artifacts = []
profiles = []
for profile, module, artifact in module_items:
    if module and module not in seen_modules:
        seen_modules.append(module)
    if artifact and artifact not in seen_artifacts:
        seen_artifacts.append(artifact)
    if profile and profile not in profiles:
        profiles.append(profile)

if not seen_modules:
    print("PROFILE=custom")
    print("MODULES=")
    print("ARTIFACTS=")
    print("CONFIDENCE=low")
    print(f"REASON={q('no Android module could be inferred from provided paths')}")
    sys.exit(0)

if profile_override:
    profile = profile_override
elif len(profiles) == 1:
    profile = profiles[0]
elif "framework-services" in profiles:
    profile = "framework-services"
elif "systemui" in profiles:
    profile = "systemui"
else:
    profile = "mixed-" + profiles[0]

confidence = "high" if len(seen_modules) == 1 and reasons else "medium"
print(f"PROFILE={q(profile)}")
print(f"MODULES={q(' '.join(seen_modules))}")
print(f"ARTIFACTS={q(' '.join(seen_artifacts))}")
print(f"CONFIDENCE={q(confidence)}")
print(f"REASON={q('; '.join(reasons[:5]))}")
PY
