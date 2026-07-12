#!/usr/bin/env bash

validator_cleanup__exit() {
  local status="${1:-1}"
  local cleanup_status=0
  trap - EXIT INT TERM HUP
  set +e
  if [[ -f "${VALIDATOR_CLEANUP_STATE_FILE:-}" ]]; then
    PYTHONDONTWRITEBYTECODE=1 python3 "$VALIDATOR_CLEANUP_HELPER" cleanup \
      --state-file "$VALIDATOR_CLEANUP_STATE_FILE"
    cleanup_status=$?
  fi
  rm -rf -- "${VALIDATOR_CLEANUP_STATE_DIR:-}"
  if [[ "$status" == "0" && "$cleanup_status" != "0" ]]; then
    status="$cleanup_status"
  fi
  exit "$status"
}

validator_cleanup_install() {
  local repo_root="$1"
  if [[ -n "${VALIDATOR_CLEANUP_ACTIVE:-}" ]]; then
    return 0
  fi
  VALIDATOR_CLEANUP_ACTIVE=1
  VALIDATOR_CLEANUP_REPO_ROOT="$(cd "$repo_root" && pwd)"
  VALIDATOR_CLEANUP_HELPER="$VALIDATOR_CLEANUP_REPO_ROOT/scripts/validator_hygiene.py"
  VALIDATOR_CLEANUP_STATE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/akbs-plugin-validator.XXXXXX")"
  VALIDATOR_CLEANUP_STATE_FILE="$VALIDATOR_CLEANUP_STATE_DIR/snapshot.json"
  VALIDATOR_CLEANUP_TMPDIR="$VALIDATOR_CLEANUP_STATE_DIR/tmp"
  mkdir -p "$VALIDATOR_CLEANUP_TMPDIR"
  export VALIDATOR_CLEANUP_REPO_ROOT VALIDATOR_CLEANUP_HELPER
  export VALIDATOR_CLEANUP_STATE_DIR VALIDATOR_CLEANUP_STATE_FILE VALIDATOR_CLEANUP_TMPDIR
  export PYTHONDONTWRITEBYTECODE=1
  case " ${PYTEST_ADDOPTS:-} " in
    *" -p no:cacheprovider "*) ;;
    *) PYTEST_ADDOPTS="${PYTEST_ADDOPTS:+$PYTEST_ADDOPTS }-p no:cacheprovider" ;;
  esac
  export PYTEST_ADDOPTS
  trap 'validator_cleanup__exit "$?"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  python3 "$VALIDATOR_CLEANUP_HELPER" snapshot \
    --repo-root "$VALIDATOR_CLEANUP_REPO_ROOT" \
    --state-file "$VALIDATOR_CLEANUP_STATE_FILE"
  python3 "$VALIDATOR_CLEANUP_HELPER" assert-pristine --repo-root "$VALIDATOR_CLEANUP_REPO_ROOT"
}
