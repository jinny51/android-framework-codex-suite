#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
ensure-build-session.sh --repo LOCAL_REPO --ssh-host HOST --remote-root PATH [options]

Ensure REMOTE_ROOT/.codex/build-session.sh exists before using a persistent
remote build session. For WSL agents, generation writes through the mounted
LOCAL_REPO path and then verifies the file on the remote Linux path.

Required:
  --repo PATH           Mounted WSL Android source path.
  --ssh-host HOST       Remote SSH target.
  --remote-root PATH    Remote Android source root.

Options:
  --force               Regenerate even if build-session.sh already exists.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

single_quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

LOCAL_REPO=""
SSH_HOST=""
REMOTE_ROOT=""
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) LOCAL_REPO="${2:-}"; shift 2 ;;
    --ssh-host) SSH_HOST="${2:-}"; shift 2 ;;
    --remote-root) REMOTE_ROOT="${2:-}"; shift 2 ;;
    --force) FORCE=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -n "$LOCAL_REPO" ]] || die "--repo is required"
[[ -d "$LOCAL_REPO" ]] || die "local repo does not exist: $LOCAL_REPO"
[[ -n "$SSH_HOST" ]] || die "--ssh-host is required"
[[ -n "$REMOTE_ROOT" ]] || die "--remote-root is required"
[[ "$REMOTE_ROOT" == /* ]] || die "--remote-root must be absolute"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_ROOT_Q="$(single_quote "$REMOTE_ROOT")"

if [[ "$FORCE" == false ]] && ssh -o BatchMode=no -o ConnectTimeout=8 "$SSH_HOST" "test -f $REMOTE_ROOT_Q/.codex/build-session.sh"; then
  echo "BUILD_SESSION_OK remote=$REMOTE_ROOT/.codex/build-session.sh existing=true"
  exit 0
fi

TMP_DISCOVERY="$(mktemp)"
trap 'rm -f "$TMP_DISCOVERY"' EXIT

"$SCRIPT_DIR/discover-project.sh" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  --output "$TMP_DISCOVERY"

"$SCRIPT_DIR/generate-build-push.sh" \
  --repo "$LOCAL_REPO" \
  --discovery-file "$TMP_DISCOVERY"

ssh -o BatchMode=no -o ConnectTimeout=8 "$SSH_HOST" "test -f $REMOTE_ROOT_Q/.codex/build-session.sh" ||
  die "generated build-session.sh is not visible on remote path: $REMOTE_ROOT/.codex/build-session.sh"

echo "BUILD_SESSION_OK remote=$REMOTE_ROOT/.codex/build-session.sh existing=false"
