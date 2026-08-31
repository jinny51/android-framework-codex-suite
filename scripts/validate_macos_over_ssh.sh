#!/usr/bin/env bash
set -euo pipefail

host="${1:?用法: scripts/validate_macos_over_ssh.sh SSH_HOST}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$repo_root/scripts/validator_cleanup.sh"
validator_cleanup_install "$repo_root"

path_guard="$repo_root/scripts/validator_path_guard.py"
remote_authority="$(
  ssh -o BatchMode=yes "$host" \
    'authority="${TMPDIR:-/private/tmp}"; cd "$authority" && pwd -P'
)"
remote_akbs_root="${AKBS_REMOTE_MAC_ROOT:-/Users/jinny/Work/AKBS}"
remote_claim="$(
  ssh -o BatchMode=yes "$host" /usr/bin/python3 - create-private \
    --authority "$remote_authority" \
    --prefix android-mac-ops-verify. \
    --purpose android-mac-ops-validator \
    --allow-shared-authority \
    --akbs-root "$remote_akbs_root" <"$path_guard"
)"
IFS=$'\t' read -r remote_tmp remote_token <<<"$remote_claim"
[[ -n "$remote_tmp" && -n "$remote_token" ]] || {
  echo "remote validator path guard did not return an owned directory" >&2
  exit 78
}
cleanup_remote() {
  ssh -o BatchMode=yes "$host" /usr/bin/python3 - cleanup-private \
    --authority "$remote_authority" \
    --path "$remote_tmp" \
    --token "$remote_token" \
    --purpose android-mac-ops-validator \
    --allow-shared-authority \
    --akbs-root "$remote_akbs_root" <"$path_guard" >/dev/null 2>&1
}
cleanup_all() {
  local status="${1:-1}"
  trap - EXIT
  if ! cleanup_remote; then
    echo "remote validator owned-directory cleanup failed" >&2
    status=78
  fi
  validator_cleanup__exit "$status"
}
trap 'cleanup_all "$?"' EXIT

(
  cd "$repo_root"
  rsync -aR \
    .agents/plugins/marketplace.json \
    manifests/android-framework-ops.toml \
    plugins/android-framework-ops/lib \
    plugins/android-framework-ops/skills/android-framework-change-workflow/scripts \
    plugins/android-framework-ops/skills/android-knowledge-intake/references/verification-acceptance-v2.json \
    plugins/android-framework-ops/skills/android-remote-build-deploy \
    plugins/android-mac-ops \
    tests/plugins/android-framework-ops/android-remote-build-deploy \
    tests/plugins/android-mac-ops \
    docs/skills/android-mac-ops \
    "$host:$remote_tmp/"
)

ssh -o BatchMode=yes "$host" /bin/bash -s -- "$remote_tmp" <<'REMOTE'
set -euo pipefail
root="$1"

[ "$(uname -s)" = "Darwin" ] || { echo "ERROR: target is not macOS" >&2; exit 2; }
printf 'MACOS_VERSION=%s\n' "$(sw_vers -productVersion)"
printf 'MACOS_ARCH=%s\n' "$(uname -m)"
printf 'MACOS_BASH=%s\n' "$(/bin/bash --version | sed -n '1p')"

while IFS= read -r script; do
  /bin/bash -n "$script"
done <<EOF
$(find "$root/plugins/android-mac-ops" "$root/plugins/android-framework-ops/skills/android-framework-change-workflow/scripts" "$root/plugins/android-framework-ops/skills/android-remote-build-deploy" -type f -name '*.sh' -print | sort)
EOF

/usr/bin/python3 -m compileall -q "$root/plugins/android-framework-ops/lib"
/usr/bin/python3 -m compileall -q "$root/plugins/android-framework-ops/skills/android-framework-change-workflow/scripts"
/usr/bin/python3 -m compileall -q "$root/plugins/android-framework-ops/skills/android-remote-build-deploy"
/usr/bin/python3 -m compileall -q "$root/tests/plugins/android-framework-ops/android-remote-build-deploy"
/usr/bin/python3 -m compileall -q "$root/tests/plugins/android-mac-ops"
cd "$root"
/usr/bin/python3 -m unittest discover \
  -s tests/plugins/android-mac-ops/android-source-access \
  -p 'test_*.py' \
  -v
/usr/bin/python3 -m unittest discover \
  -s tests/plugins/android-framework-ops/android-remote-build-deploy \
  -p 'test_*.py' \
  -v

echo "MACOS_REMOTE_VALIDATION=PASS"
REMOTE
