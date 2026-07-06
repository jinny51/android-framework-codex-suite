#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(cd "$script_dir/.." && pwd)"

pass() {
  echo "PASS: $*"
}

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require_contains() {
  local haystack="$1"
  local needle="$2"
  local label="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    pass "$label"
  else
    echo "$haystack" >&2
    fail "$label"
  fi
}

tmp_dir="$(mktemp -d /tmp/android-source-cifs-validate.XXXXXX)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

bash -n "$script_dir"/*.sh
pass "scripts bash syntax"

plan_env="$tmp_dir/plan.env"
"$script_dir/plan-from-remote-path.sh" \
  --remote-root /home/test55/work/unisoc/rk3576 \
  >"$plan_env"
# shellcheck disable=SC1090
source "$plan_env"
[ "$REMOTE_ROOT" = "/home/test55/work/unisoc/rk3576" ] || fail "plan preserves remote root"
[ "$REMOTE_USER" = "test55" ] || fail "plan derives remote user"
[ -z "$PLATFORM" ] || fail "plan must not infer platform from path"
[ -z "$SDK_NAME" ] || fail "plan must not infer SDK name from path"
pass "plan does not infer platform/project from path"

plan_override_env="$tmp_dir/plan-override.env"
"$script_dir/plan-from-remote-path.sh" \
  --remote-root /home/test55/work/unisoc/rk3576 \
  --local-platform rk \
  --sdk-name TVA10A2R \
  >"$plan_override_env"
# shellcheck disable=SC1090
source "$plan_override_env"
[ "$PLATFORM" = "rk" ] || fail "plan honors explicit platform"
[ "$SDK_NAME" = "TVA10A2R" ] || fail "plan honors explicit SDK name"
pass "plan honors explicit overrides"

ensure_help="$("$script_dir/ensure-samba-share.sh" --help)"
require_contains "$ensure_help" "Default share plan:" "ensure-samba-share documents default share plan"
require_contains "$ensure_help" "[rk3576] path = /home/test55/work/unisoc/rk3576" "ensure-samba-share default is project-level"
require_contains "$ensure_help" "Parent/platform shares are explicit exceptions" "ensure-samba-share documents parent share exception"

mount_help="$("$script_dir/mount-from-remote-path.sh" --help)"
require_contains "$mount_help" "--accept-platform-conflict" "mount flow exposes platform conflict acceptance"
require_contains "$mount_help" "--accept-sdk-name-conflict" "mount flow exposes SDK conflict acceptance"
require_contains "$mount_help" "This is the default" "mount flow documents project-level default"

set +e
inspect_missing_accept_output="$("$script_dir/inspect-android-sdk.sh" \
  --ssh-host dummy \
  --remote-root /home/test55/work/unisoc/rk3576 \
  --accept-platform-conflict 2>&1)"
inspect_missing_accept_status=$?
set -e
[ "$inspect_missing_accept_status" -eq 2 ] || fail "inspect rejects accept-platform-conflict without --platform"
require_contains "$inspect_missing_accept_output" "--accept-platform-conflict requires --platform" "inspect validates platform acceptance precondition"

if command -v rg >/dev/null 2>&1; then
  if rg -n --glob '!**/validate-skill.sh' 'initial platform mount|SAMBA_PROJECT_URL is for reference|share-or-sdk|Use `SAMBA_SHARE_URL`|Capability Capture Candidate|Pattern:|Store in:|Persist\\?' "$skill_dir" >/tmp/android-source-cifs-validate-rg.out 2>&1; then
    cat /tmp/android-source-cifs-validate-rg.out >&2
    fail "old framework/output residue scan"
  fi
  pass "old framework/output residue scan"
fi

if [ -n "${VALIDATE_REMOTE_SSH:-}" ] && [ -n "${VALIDATE_REMOTE_ROOT:-}" ]; then
  remote_env="$tmp_dir/remote-inspect.env"
  "$script_dir/inspect-android-sdk.sh" \
    --ssh-host "$VALIDATE_REMOTE_SSH" \
    --remote-root "$VALIDATE_REMOTE_ROOT" \
    >"$remote_env"
  # shellcheck disable=SC1090
  source "$remote_env"
  [ -n "$PLATFORM" ] || fail "remote inspect produced platform"
  [ -n "$SDK_NAME" ] || fail "remote inspect produced SDK name"
  pass "remote inspect produced $PLATFORM/$SDK_NAME"

  if [ "$PLATFORM" != "unisoc" ]; then
    set +e
    "$script_dir/inspect-android-sdk.sh" \
      --ssh-host "$VALIDATE_REMOTE_SSH" \
      --remote-root "$VALIDATE_REMOTE_ROOT" \
      --platform unisoc \
      >/tmp/android-source-cifs-validate-conflict.out 2>&1
    conflict_status=$?
    set -e
    [ "$conflict_status" -eq 7 ] || fail "remote platform conflict exits 7"
    pass "remote platform conflict exits 7"

    "$script_dir/inspect-android-sdk.sh" \
      --ssh-host "$VALIDATE_REMOTE_SSH" \
      --remote-root "$VALIDATE_REMOTE_ROOT" \
      --platform unisoc \
      --accept-platform-conflict \
      >/tmp/android-source-cifs-validate-accepted.out
    pass "remote platform conflict can be explicitly accepted"
  fi

  if [ "$SDK_NAME" != "ManualName" ]; then
    set +e
    "$script_dir/inspect-android-sdk.sh" \
      --ssh-host "$VALIDATE_REMOTE_SSH" \
      --remote-root "$VALIDATE_REMOTE_ROOT" \
      --sdk-name ManualName \
      >/tmp/android-source-cifs-validate-sdk-conflict.out 2>&1
    sdk_conflict_status=$?
    set -e
    [ "$sdk_conflict_status" -eq 8 ] || fail "remote SDK name conflict exits 8"
    pass "remote SDK name conflict exits 8"

    "$script_dir/inspect-android-sdk.sh" \
      --ssh-host "$VALIDATE_REMOTE_SSH" \
      --remote-root "$VALIDATE_REMOTE_ROOT" \
      --sdk-name ManualName \
      --accept-sdk-name-conflict \
      >/tmp/android-source-cifs-validate-sdk-accepted.out
    pass "remote SDK name conflict can be explicitly accepted"
  fi
else
  echo "SKIP: remote inspect checks; set VALIDATE_REMOTE_SSH and VALIDATE_REMOTE_ROOT to enable"
fi

echo "skill 校验通过"
