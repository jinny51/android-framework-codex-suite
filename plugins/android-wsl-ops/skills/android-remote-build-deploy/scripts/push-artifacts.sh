#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
push-artifacts.sh --artifact PATH [--dest DEVICE_PATH] [options]

Push built Android artifacts to the locally USB-connected device.

Options:
  --artifact PATH       Add an artifact to push. Repeatable.
  --dest DEVICE_PATH    Destination for the previous artifact. Optional only when
                        --product-out can infer it from system/product/vendor paths.
  --product-out PATH    Product out path used to infer device destination from partition path.
  --destinations-file FILE
                        Project-local artifact destination memory file.
  --learn-destinations  After successful push, update --destinations-file with artifact rel -> device path mappings.
  --adb-serial SERIAL   Local adb serial used for this delivery.
  --evidence-out FILE   Write verification_result evidence JSON for patch capture.
  --remote-build-host HOST
                        Remote build host that produced the artifact.
  --remote-source-root PATH
                        Remote Android source root used for the build.
  --remote-build-command CMD
                        Remote build command used for the artifact.
  --remote-build-profile PROFILE
                        Remote build profile or module group.
  --remote-artifact PATH
                        Remote artifact path. Repeatable.
  --artifact-sha1 SHA1  SHA1 for the corresponding --remote-artifact. Repeatable.
  --artifact-transfer TEXT
                        How the artifact moved from remote build server to local WSL.
  --reboot             Reboot after push.
  --wait-boot          Wait for boot completion after reboot.
  --dry-run            Print intended push operations only.

Environment:
  ADB                  adb command. Can be adb, adb.exe, or /mnt/c/.../adb.exe.

Examples:
  ADB=/mnt/c/Android/platform-tools/adb.exe push-artifacts.sh \
    --artifact /mnt/repo/out/target/product/foo/system/framework/services.jar --reboot
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

ADB="${ADB:-adb}"
PRODUCT_OUT=""
DESTINATIONS_FILE=""
LEARN_DESTINATIONS=false
REBOOT=false
WAIT_BOOT=false
DRY_RUN=false
ADB_SERIAL=""
EVIDENCE_OUT="${CODEX_BUILD_DELIVERY_EVIDENCE:-}"
REMOTE_BUILD_HOST=""
REMOTE_SOURCE_ROOT=""
REMOTE_BUILD_COMMAND=""
REMOTE_BUILD_PROFILE=""
ARTIFACT_TRANSFER=""
ARTIFACTS=()
DESTS=()
REMOTE_ARTIFACTS=()
ARTIFACT_SHA1S=()

last_artifact_index() {
  echo "$((${#ARTIFACTS[@]} - 1))"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact)
      ARTIFACTS+=("${2:-}")
      DESTS+=("")
      shift 2
      ;;
    --dest)
      [[ ${#ARTIFACTS[@]} -gt 0 ]] || die "--dest must follow --artifact"
      DESTS[$(last_artifact_index)]="${2:-}"
      shift 2
      ;;
    --product-out) PRODUCT_OUT="${2:-}"; shift 2 ;;
    --destinations-file) DESTINATIONS_FILE="${2:-}"; shift 2 ;;
    --learn-destinations) LEARN_DESTINATIONS=true; shift ;;
    --adb-serial) ADB_SERIAL="${2:-}"; shift 2 ;;
    --evidence-out) EVIDENCE_OUT="${2:-}"; shift 2 ;;
    --remote-build-host) REMOTE_BUILD_HOST="${2:-}"; shift 2 ;;
    --remote-source-root) REMOTE_SOURCE_ROOT="${2:-}"; shift 2 ;;
    --remote-build-command) REMOTE_BUILD_COMMAND="${2:-}"; shift 2 ;;
    --remote-build-profile) REMOTE_BUILD_PROFILE="${2:-}"; shift 2 ;;
    --remote-artifact) REMOTE_ARTIFACTS+=("${2:-}"); shift 2 ;;
    --artifact-sha1) ARTIFACT_SHA1S+=("${2:-}"); shift 2 ;;
    --artifact-transfer) ARTIFACT_TRANSFER="${2:-}"; shift 2 ;;
    --reboot) REBOOT=true; shift ;;
    --wait-boot) WAIT_BOOT=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ ${#ARTIFACTS[@]} -gt 0 ]] || die "At least one --artifact is required"

declare -A CODEX_ARTIFACT_DESTINATIONS=()
if [[ -n "$DESTINATIONS_FILE" && -f "$DESTINATIONS_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$DESTINATIONS_FILE"
fi

adb_cmd_path() {
  command -v "$ADB" 2>/dev/null || true
}

is_windows_adb() {
  local resolved
  resolved="$(adb_cmd_path)"
  [[ "$ADB" == *.exe || "$resolved" == *.exe ]]
}

path_for_adb() {
  local path="$1"
  if is_windows_adb && command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$path"
  else
    printf "%s" "$path"
  fi
}

infer_dest() {
  local artifact="$1"
  local rel

  if [[ -n "$PRODUCT_OUT" ]]; then
    PRODUCT_OUT="${PRODUCT_OUT%/}"
    if [[ "$artifact" == "$PRODUCT_OUT/"* ]]; then
      rel="${artifact#"$PRODUCT_OUT"/}"
      if [[ -n "${CODEX_ARTIFACT_DESTINATIONS[$rel]+set}" ]]; then
        printf "%s" "${CODEX_ARTIFACT_DESTINATIONS[$rel]}"
        return 0
      fi
      case "$rel" in
        system/*|system_ext/*|product/*|vendor/*|odm/*)
          printf "/%s" "$rel"
          return 0
          ;;
      esac
    fi
  fi

  return 1
}

artifact_rel() {
  local artifact="$1"
  if [[ -n "$PRODUCT_OUT" ]]; then
    PRODUCT_OUT="${PRODUCT_OUT%/}"
    if [[ "$artifact" == "$PRODUCT_OUT/"* ]]; then
      printf "%s" "${artifact#"$PRODUCT_OUT"/}"
      return 0
    fi
  fi
  return 1
}

write_destinations_file() {
  [[ -n "$DESTINATIONS_FILE" ]] || return 0
  mkdir -p "$(dirname "$DESTINATIONS_FILE")"
  local tmp key
  tmp="$(mktemp)"
  {
    echo "#!/usr/bin/env bash"
    echo "# Project-local artifact destination memory. Generated by push-artifacts.sh."
    echo "declare -A CODEX_ARTIFACT_DESTINATIONS=()"
    while IFS= read -r key; do
      [[ -n "$key" ]] || continue
      printf "CODEX_ARTIFACT_DESTINATIONS[%q]=%q\n" "$key" "${CODEX_ARTIFACT_DESTINATIONS[$key]}"
    done < <(printf "%s\n" "${!CODEX_ARTIFACT_DESTINATIONS[@]}" | sort)
  } >"$tmp"
  mv "$tmp" "$DESTINATIONS_FILE"
  chmod +x "$DESTINATIONS_FILE"
}

learn_destination() {
  local artifact="$1"
  local dest="$2"
  local rel
  [[ "$LEARN_DESTINATIONS" == true ]] || return 0
  [[ -n "$DESTINATIONS_FILE" ]] || die "--learn-destinations requires --destinations-file"
  rel="$(artifact_rel "$artifact" || true)"
  [[ -n "$rel" ]] || return 0
  CODEX_ARTIFACT_DESTINATIONS[$rel]="$dest"
  write_destinations_file
  echo "DESTINATION_MEMORY artifact_rel=$rel dest=$dest file=$DESTINATIONS_FILE"
}

run_adb() {
  if [[ "$DRY_RUN" == true ]]; then
    printf "ADB"
    if [[ -n "$ADB_SERIAL" ]]; then
      printf " -s %q" "$ADB_SERIAL"
    fi
    printf " %q" "$@"
    printf "\n"
  elif [[ -n "$ADB_SERIAL" ]]; then
    "$ADB" -s "$ADB_SERIAL" "$@"
  else
    "$ADB" "$@"
  fi
}

default_evidence_out() {
  if [[ -n "$EVIDENCE_OUT" ]]; then
    printf "%s" "$EVIDENCE_OUT"
    return 0
  fi
  if [[ -n "$DESTINATIONS_FILE" && "$DESTINATIONS_FILE" == *"/.codex/"* ]]; then
    local prefix="${DESTINATIONS_FILE%%/.codex/*}"
    printf "%s/.codex/evidence/latest-build-delivery.json" "$prefix"
    return 0
  fi
  if [[ -d "$PWD/.codex" ]]; then
    printf "%s/.codex/evidence/latest-build-delivery.json" "$PWD"
    return 0
  fi
  return 1
}

join_lines() {
  if [[ $# -eq 0 ]]; then
    return 0
  fi
  printf "%s\n" "$@"
}

write_delivery_evidence() {
  local target
  target="$(default_evidence_out || true)"
  [[ -n "$target" ]] || return 0
  mkdir -p "$(dirname "$target")"
  CODEX_LOCAL_ARTIFACTS="$(join_lines "${ARTIFACTS[@]}")" \
  CODEX_PUSH_PAIRS="$(join_lines "${PUSH_PAIRS[@]}")" \
  CODEX_REMOTE_ARTIFACTS="$(join_lines "${REMOTE_ARTIFACTS[@]}")" \
  CODEX_ARTIFACT_SHA1S="$(join_lines "${ARTIFACT_SHA1S[@]}")" \
  CODEX_REBOOT="$REBOOT" \
  CODEX_WAIT_BOOT="$WAIT_BOOT" \
  CODEX_DRY_RUN="$DRY_RUN" \
  CODEX_ADB_SERIAL="$ADB_SERIAL" \
  CODEX_REMOTE_BUILD_HOST="$REMOTE_BUILD_HOST" \
  CODEX_REMOTE_SOURCE_ROOT="$REMOTE_SOURCE_ROOT" \
  CODEX_REMOTE_BUILD_COMMAND="$REMOTE_BUILD_COMMAND" \
  CODEX_REMOTE_BUILD_PROFILE="$REMOTE_BUILD_PROFILE" \
  CODEX_ARTIFACT_TRANSFER="$ARTIFACT_TRANSFER" \
  python3 - "$target" <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def lines(name: str) -> list[str]:
    value = os.environ.get(name, "")
    return [item for item in value.splitlines() if item]


target = Path(sys.argv[1])
local_artifacts = lines("CODEX_LOCAL_ARTIFACTS")
push_pairs = lines("CODEX_PUSH_PAIRS")
remote_paths = lines("CODEX_REMOTE_ARTIFACTS")
sha1s = lines("CODEX_ARTIFACT_SHA1S")
adb_serial = os.environ.get("CODEX_ADB_SERIAL", "")
adb_prefix = f"adb -s {adb_serial}" if adb_serial else "adb"
remote_artifacts = []
for index, path in enumerate(remote_paths):
    remote_artifacts.append({"path": path, "sha1": sha1s[index] if index < len(sha1s) else ""})
adb_actions = []
for pair in push_pairs:
    artifact, _, dest = pair.partition("|")
    if artifact and dest:
        adb_actions.append(f"{adb_prefix} push {artifact} {dest}")
device_restarts = []
if os.environ.get("CODEX_REBOOT") == "true":
    device_restarts.append(f"{adb_prefix} reboot")
if os.environ.get("CODEX_WAIT_BOOT") == "true":
    device_restarts.append(f"{adb_prefix} wait-for-device")
payload = {
    "kind": "verification_result",
    "result": "INFO" if os.environ.get("CODEX_DRY_RUN") == "true" else "PASS",
    "method": "device",
    "summary": "remote build artifact delivered to local adb device" if os.environ.get("CODEX_DRY_RUN") != "true" else "dry-run remote build artifact delivery evidence",
    "build": [],
    "device": adb_serial,
    "steps": adb_actions + device_restarts,
    "remote_build": {
        "host": os.environ.get("CODEX_REMOTE_BUILD_HOST", ""),
        "source_root": os.environ.get("CODEX_REMOTE_SOURCE_ROOT", ""),
        "command": os.environ.get("CODEX_REMOTE_BUILD_COMMAND", ""),
        "profile": os.environ.get("CODEX_REMOTE_BUILD_PROFILE", ""),
        "artifacts": remote_artifacts,
    },
    "local_delivery": {
        "transfer": os.environ.get("CODEX_ARTIFACT_TRANSFER", ""),
        "local_artifacts": local_artifacts,
        "adb_serial": adb_serial,
        "adb_actions": adb_actions,
        "device_restarts": device_restarts,
    },
}
target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  echo "EVIDENCE $target"
}

command -v "$ADB" >/dev/null 2>&1 || [[ -x "$ADB" ]] || die "adb not found. Set ADB=/path/to/adb or adb.exe."

PUSH_PAIRS=()
for i in "${!ARTIFACTS[@]}"; do
  artifact="${ARTIFACTS[$i]}"
  [[ -f "$artifact" ]] || die "artifact not found: $artifact"
  dest="${DESTS[$i]}"
  if [[ -z "$dest" ]]; then
    dest="$(infer_dest "$artifact" || true)"
  fi
  [[ -n "$dest" ]] || die "Cannot infer destination for $artifact; provide --dest"
  PUSH_PAIRS+=("$artifact|$dest")
done

if [[ "$DRY_RUN" == false ]]; then
  run_adb wait-for-device >/dev/null
fi
run_adb root >/dev/null || true
run_adb remount >/dev/null

for pair in "${PUSH_PAIRS[@]}"; do
  artifact="${pair%%|*}"
  dest="${pair#*|}"
  host_path="$(path_for_adb "$artifact")"
  echo "PUSH $artifact -> $dest"
  run_adb push "$host_path" "$dest" >/dev/null
  if [[ "$DRY_RUN" == false ]]; then
    learn_destination "$artifact" "$dest"
  fi
done

run_adb shell sync >/dev/null || true

if [[ "$REBOOT" == true ]]; then
  run_adb reboot
  if [[ "$WAIT_BOOT" == true ]]; then
    run_adb wait-for-device
    if [[ "$DRY_RUN" == false ]]; then
      until [[ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; do
        sleep 1
      done
    fi
    echo "BOOT_OK"
  fi
fi

write_delivery_evidence
echo "PUSH_OK count=${#PUSH_PAIRS[@]}"
