#!/usr/bin/env bash
set -euo pipefail

host="${1:?用法: scripts/validate_macos_over_ssh.sh SSH_HOST}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

remote_tmp="$(ssh -o BatchMode=yes "$host" 'mktemp -d "${TMPDIR:-/tmp}/android-mac-ops-verify.XXXXXX"')"
cleanup() {
  ssh -o BatchMode=yes "$host" /bin/rm -rf -- "$remote_tmp" >/dev/null 2>&1 || true
}
trap cleanup EXIT

(
  cd "$repo_root"
  rsync -aR \
    plugins/android-mac-ops \
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
$(find "$root/plugins/android-mac-ops" -type f -name '*.sh' -print | sort)
EOF

/usr/bin/python3 -m compileall -q "$root/tests/plugins/android-mac-ops"
cd "$root"
/usr/bin/python3 -m unittest discover \
  -s tests/plugins/android-mac-ops/android-source-access \
  -p 'test_*.py' \
  -v

echo "MACOS_REMOTE_VALIDATION=PASS"
REMOTE
