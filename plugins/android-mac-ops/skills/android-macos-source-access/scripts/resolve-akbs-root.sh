#!/usr/bin/env bash
set -euo pipefail
# Resolve the local AKBS system root on macOS.
# This is separate from the SMB/Samba source mount root.

root="${AKBS_ROOT:-/Users/jinny/Work/AKBS}"

printf 'AKBS_ROOT=%s\n' "$root"
