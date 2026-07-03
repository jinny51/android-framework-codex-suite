#!/usr/bin/env bash
set -euo pipefail
# Resolve the macOS SMB/Samba source mount root.
# Do not use AKBS_ROOT for source share mounts.

root="${SAMBA_SOURCE_ROOT:-${ANDROID_MACOS_SAMBA_ROOT:-/Users/jinny/Work/Samba}}"

printf 'SAMBA_SOURCE_ROOT=%s\n' "$root"
