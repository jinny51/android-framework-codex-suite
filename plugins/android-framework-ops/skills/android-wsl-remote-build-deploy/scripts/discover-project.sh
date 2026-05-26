#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
discover-project.sh --ssh-host HOST --remote-root PATH [options]

Discover Android remote build settings.

Required:
  --ssh-host HOST        SSH host alias, hostname, or user@host.
  --remote-root PATH     Absolute source path on the remote build server.

Optional:
  --ssh-user USER        SSH user when HOST is not already user@host.
  --output FILE          Write shell config to FILE instead of stdout.
  --max-depth N          Reserved for compatibility. Lunch discovery is limited
                         to root-level build scripts.
  --ignore-repo-config   Ignore remote .codex/build-push.config.sh and infer from source scripts only.

Environment:
  SSHPASS                If set and sshpass exists, use it for SSH password auth.

The script prints shell-style KEY=VALUE lines. It does not write secrets.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

shell_quote() {
  printf "%q" "$1"
}

single_quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

SSH_HOST=""
SSH_USER=""
REMOTE_ROOT=""
OUTPUT=""
MAX_DEPTH=5
IGNORE_REPO_CONFIG=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-host) SSH_HOST="${2:-}"; shift 2 ;;
    --ssh-user) SSH_USER="${2:-}"; shift 2 ;;
    --remote-root) REMOTE_ROOT="${2:-}"; shift 2 ;;
    --output) OUTPUT="${2:-}"; shift 2 ;;
    --max-depth) MAX_DEPTH="${2:-}"; shift 2 ;;
    --ignore-repo-config) IGNORE_REPO_CONFIG=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -n "$SSH_HOST" ]] || die "--ssh-host is required"
[[ -n "$REMOTE_ROOT" ]] || die "--remote-root is required"
[[ "$REMOTE_ROOT" == /* ]] || die "--remote-root must be absolute"

SSH_TARGET="$SSH_HOST"
if [[ -n "$SSH_USER" && "$SSH_HOST" != *@* ]]; then
  SSH_TARGET="${SSH_USER}@${SSH_HOST}"
fi

ssh_run() {
  local cmd="$1"
  local ssh_args=(-o BatchMode=no -o ConnectTimeout=8 "$SSH_TARGET" "$cmd")
  if [[ -n "${SSHPASS:-}" ]] && command -v sshpass >/dev/null 2>&1; then
    SSHPASS="$SSHPASS" sshpass -e ssh "${ssh_args[@]}"
  else
    ssh "${ssh_args[@]}"
  fi
}

parse_build_hints() {
  local hints_file="$1"
  python3 - "$hints_file" <<'PY'
import collections
import re
import sys

entries = []
text_parts = []
for raw in open(sys.argv[1], "r", encoding="utf-8", errors="ignore"):
    if raw.startswith("__CODEX_ENTRY_SCRIPT__="):
        entry = raw.split("=", 1)[1].strip()
        if entry:
            entries.append(entry)
        continue
    text_parts.append(raw)
text = "".join(text_parts)

envsetup = "build/envsetup.sh"
env_matches = re.findall(r"(?:source|\.)\s+([./A-Za-z0-9_-]*build/envsetup\.sh)", text)
if env_matches:
    envsetup = env_matches[0].lstrip("./")

lunches = []
for match in re.findall(r"\blunch\s+([A-Za-z0-9_.+-]+)", text):
    if "$" not in match and match not in {"lunch", "combo"}:
        lunches.append(match)
lunch = collections.Counter(lunches).most_common(1)[0][0] if lunches else ""

products = []
for match in re.findall(r"out/target/product/([A-Za-z0-9_.-]+)", text):
    products.append(match)
product = collections.Counter(products).most_common(1)[0][0] if products else ""
if not product and lunch:
    product = lunch.split("-", 1)[0]

print(f"ENVSETUP_SCRIPT={envsetup!r}")
if entries:
    print(f"BUILD_ENTRY_SCRIPT={entries[0]!r}")
if lunch:
    print(f"LUNCH_TARGET={lunch!r}")
if product:
    print(f"PRODUCT_OUT_DIR_REL={'out/target/product/' + product!r}")
PY
}

parse_project_config() {
  local config_file="$1"
  python3 - "$config_file" <<'PY'
import ast
import re
import sys

allowed = {
    "SSH_HOST",
    "REMOTE_ROOT",
    "ENVSETUP_SCRIPT",
    "LUNCH_TARGET",
    "PRODUCT_OUT_DIR_REL",
    "BUILD_PUSH_LOG_REL",
}

for raw in open(sys.argv[1], "r", encoding="utf-8", errors="ignore"):
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if key not in allowed:
        continue
    value = value.strip()
    if not value:
        continue
    try:
        if value[0] in ("'", '"'):
            parsed = ast.literal_eval(value)
        else:
            parsed = value.split("#", 1)[0].strip()
    except Exception:
        parsed = value.strip("'\"")
    print(f"{key}={parsed!r}")
PY
}

REMOTE_ROOT_Q="$(single_quote "$REMOTE_ROOT")"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

REMOTE_CONFIG_FILE="$TMP_DIR/build-push.config.sh"
if [[ "$IGNORE_REPO_CONFIG" == false ]]; then
  REMOTE_CONFIG_CMD="
cd $REMOTE_ROOT_Q || exit 2
test -r .codex/build-push.config.sh && sed -n '1,180p' .codex/build-push.config.sh || true
"
  if ssh_run "$REMOTE_CONFIG_CMD" >"$REMOTE_CONFIG_FILE" 2>/dev/null; then
    :
  else
    : >"$REMOTE_CONFIG_FILE"
  fi
else
  : >"$REMOTE_CONFIG_FILE"
fi

CONFIG_OUTPUT=""
if [[ -s "$REMOTE_CONFIG_FILE" ]] && command -v python3 >/dev/null 2>&1; then
  CONFIG_OUTPUT="$(parse_project_config "$REMOTE_CONFIG_FILE" || true)"
fi

HINTS_FILE="$TMP_DIR/root-build-hints.txt"
REMOTE_HINT_CMD="
cd $REMOTE_ROOT_Q || exit 2
{
  find . -maxdepth 1 -type f -name 'debug.sh' 2>/dev/null
  find . -maxdepth 1 -type f -name 'debug*.sh' ! -name 'debug.sh' 2>/dev/null | sort
  find . -maxdepth 1 -type f -name '*.sh' ! -name 'debug*.sh' 2>/dev/null | sort
} | awk '!seen[\$0]++' |
while IFS= read -r f; do
  printf '__CODEX_ENTRY_SCRIPT__=%s\n' \"\${f#./}\"
  grep -HnE 'source[[:space:]]+.*build/envsetup|^[[:space:]]*\\.[[:space:]]+.*build/envsetup|lunch[[:space:]]+|out/target/product|TARGET_PRODUCT|TARGET_BUILD_VARIANT|\\bmka\\b|\\bmake\\b|\\bm[[:space:]]+' \"\$f\" 2>/dev/null || true
done | head -n 1000
"
if ssh_run "$REMOTE_HINT_CMD" >"$HINTS_FILE" 2>/dev/null; then
  :
else
  : >"$HINTS_FILE"
fi

BUILD_OUTPUT=""
if [[ -s "$HINTS_FILE" ]] && command -v python3 >/dev/null 2>&1; then
  BUILD_OUTPUT="$(parse_build_hints "$HINTS_FILE" || true)"
fi

extract_value() {
  local key="$1"
  local data="$2"
  printf "%s\n" "$data" | awk -F= -v key="$key" '$1==key{
    value=$0
    sub("^[^=]*=", "", value)
    gsub(/^'\''|'\''$/, "", value)
    print value
    exit
  }'
}

ENVSETUP_SCRIPT="$(extract_value ENVSETUP_SCRIPT "$CONFIG_OUTPUT")"
LUNCH_TARGET="$(extract_value LUNCH_TARGET "$CONFIG_OUTPUT")"
PRODUCT_OUT_DIR_REL="$(extract_value PRODUCT_OUT_DIR_REL "$CONFIG_OUTPUT")"
BUILD_PUSH_LOG_REL="$(extract_value BUILD_PUSH_LOG_REL "$CONFIG_OUTPUT")"
BUILD_ENTRY_SCRIPT="$(extract_value BUILD_ENTRY_SCRIPT "$BUILD_OUTPUT")"

ENVSETUP_SCRIPT="${ENVSETUP_SCRIPT:-$(extract_value ENVSETUP_SCRIPT "$BUILD_OUTPUT")}"
LUNCH_TARGET="${LUNCH_TARGET:-$(extract_value LUNCH_TARGET "$BUILD_OUTPUT")}"
PRODUCT_OUT_DIR_REL="${PRODUCT_OUT_DIR_REL:-$(extract_value PRODUCT_OUT_DIR_REL "$BUILD_OUTPUT")}"
ENVSETUP_SCRIPT="${ENVSETUP_SCRIPT:-build/envsetup.sh}"

VERIFY_PRODUCT_OUT=""
if [[ -n "$LUNCH_TARGET" ]]; then
  ENV_Q="$(single_quote "$ENVSETUP_SCRIPT")"
  LUNCH_Q="$(single_quote "$LUNCH_TARGET")"
  VERIFY_CMD="
cd $REMOTE_ROOT_Q || exit 2
source $ENV_Q >/dev/null 2>&1
lunch $LUNCH_Q >/dev/null 2>&1
get_build_var PRODUCT_OUT 2>/dev/null | tail -n 1
"
  VERIFY_PRODUCT_OUT="$(ssh_run "$VERIFY_CMD" 2>/dev/null || true)"
  VERIFY_PRODUCT_OUT="$(printf "%s" "$VERIFY_PRODUCT_OUT" | tail -n 1)"
  if [[ -n "$VERIFY_PRODUCT_OUT" ]]; then
    if [[ "$VERIFY_PRODUCT_OUT" == "$REMOTE_ROOT/"* ]]; then
      PRODUCT_OUT_DIR_REL="${VERIFY_PRODUCT_OUT#"$REMOTE_ROOT"/}"
    elif [[ "$VERIFY_PRODUCT_OUT" == out/target/product/* ]]; then
      PRODUCT_OUT_DIR_REL="$VERIFY_PRODUCT_OUT"
    fi
  fi
fi

DISCOVERY_STATUS="partial"
if [[ -n "$LUNCH_TARGET" && -n "$PRODUCT_OUT_DIR_REL" ]]; then
  DISCOVERY_STATUS="complete"
fi

OUT_FILE="${OUTPUT:-/dev/stdout}"
{
  printf "DISCOVERY_STATUS=%s\n" "$(shell_quote "$DISCOVERY_STATUS")"
  printf "SSH_HOST=%s\n" "$(shell_quote "$SSH_TARGET")"
  printf "REMOTE_ROOT=%s\n" "$(shell_quote "$REMOTE_ROOT")"
  printf "DISCOVERY_HINT_SCOPE=%s\n" "$(shell_quote "root-level debug*.sh first")"
  if [[ -n "${BUILD_ENTRY_SCRIPT:-}" ]]; then
    printf "BUILD_ENTRY_SCRIPT=%s\n" "$(shell_quote "$BUILD_ENTRY_SCRIPT")"
  fi
  printf "ENVSETUP_SCRIPT=%s\n" "$(shell_quote "$ENVSETUP_SCRIPT")"
  if [[ -n "$LUNCH_TARGET" ]]; then
    printf "LUNCH_TARGET=%s\n" "$(shell_quote "$LUNCH_TARGET")"
  fi
  if [[ -n "$PRODUCT_OUT_DIR_REL" ]]; then
    printf "PRODUCT_OUT_DIR_REL=%s\n" "$(shell_quote "$PRODUCT_OUT_DIR_REL")"
  fi
  if [[ -n "${BUILD_PUSH_LOG_REL:-}" ]]; then
    printf "BUILD_PUSH_LOG_REL=%s\n" "$(shell_quote "$BUILD_PUSH_LOG_REL")"
  fi
  if [[ -n "$VERIFY_PRODUCT_OUT" ]]; then
    printf "VERIFIED_PRODUCT_OUT=%s\n" "$(shell_quote "$VERIFY_PRODUCT_OUT")"
  fi
} >"$OUT_FILE"

if [[ "$DISCOVERY_STATUS" != "complete" ]]; then
  echo "WARN: discovery is partial; inspect $HINTS_FILE or provide lunch/product out explicitly." >&2
fi
