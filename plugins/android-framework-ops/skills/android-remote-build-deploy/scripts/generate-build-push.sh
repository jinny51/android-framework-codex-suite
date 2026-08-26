#!/usr/bin/env bash
set -euo pipefail

cat >&2 <<'EOF'
ERROR: generate-build-push.sh was retired by remote workspace protocol v2.
It must not generate wrappers or profiles through an SMB/CIFS mount.

Use scripts/remote-build-v2.py with these channel-backed actions:
  install
  configure --lunch ... --product-out ...
  profile-set --profile ... --modules ... --artifact 'MODULE=RELATIVE|DEST'
EOF
exit 64
