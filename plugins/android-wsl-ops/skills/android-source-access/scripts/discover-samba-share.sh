#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  discover-samba-share.sh --ssh-host <user@server|server> --remote-root /remote/source/path [options]

Options:
  --ssh-host HOST       SSH host used to read /etc/samba/smb.conf.
  --remote-root PATH    Remote source path to map to a Samba share.
  --server-name NAME    Host/IP to use in the final //server/share URL. Defaults to ssh -G HostName, then SSH host without user.
  --smb-conf PATH       Samba config path on the server. Default: /etc/samba/smb.conf.
  -h, --help            Show this help.

Output:
  Prints shell-style KEY=VALUE lines by default:
    SAMBA_SHARE_URL     Matched share-root URL, for example //server/work.
    SAMBA_PROJECT_URL   Remote SDK root URL, for example //server/work/rk/project.
    SAMBA_PROJECT_REL   Project path relative to the share root.
USAGE
}

ssh_host=
remote_root=
server_name=
smb_conf=/etc/samba/smb.conf

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ssh-host) ssh_host="${2:?missing value for --ssh-host}"; shift 2 ;;
    --remote-root) remote_root="${2:?missing value for --remote-root}"; shift 2 ;;
    --server-name) server_name="${2:?missing value for --server-name}"; shift 2 ;;
    --smb-conf) smb_conf="${2:?missing value for --smb-conf}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$ssh_host" ] || { echo "--ssh-host is required" >&2; exit 2; }
[ -n "$remote_root" ] || { echo "--remote-root is required" >&2; exit 2; }

if [ -z "$server_name" ]; then
  server_name="$(ssh -G "$ssh_host" 2>/dev/null | awk '$1 == "hostname" {print $2; exit}' || true)"
  if [ -z "$server_name" ]; then
    server_name="${ssh_host#*@}"
  fi
fi

conf="$(ssh "$ssh_host" "test -r '$smb_conf' && cat '$smb_conf'")"
conf_file="$(mktemp)"
trap 'rm -f "$conf_file"' EXIT
printf "%s\n" "$conf" >"$conf_file"

python3 - "$remote_root" "$server_name" "$conf_file" <<'PY'
import posixpath
import re
import shlex
import sys

remote_root, server, conf_path = sys.argv[1], sys.argv[2], sys.argv[3]
remote_root = posixpath.normpath(remote_root)
section = None
shares = []

with open(conf_path, "r", encoding="utf-8", errors="ignore") as fh:
    lines = list(fh)

for raw in lines:
    line = raw.strip()
    if not line or line.startswith(("#", ";")):
        continue
    match = re.match(r"\[([^\]]+)\]", line)
    if match:
        section = match.group(1).strip()
        continue
    if section is None or section.lower() in {"global", "printers", "print$"}:
        continue
    path_match = re.match(r"(?i)path\s*=\s*(.+)", line)
    if not path_match:
        continue
    path = posixpath.normpath(path_match.group(1).strip())
    if path:
        shares.append((section, path))

best = None
for name, path in shares:
    if remote_root == path or remote_root.startswith(path.rstrip("/") + "/"):
        if best is None or len(path) > len(best[1]):
            best = (name, path)

if best is None:
    print(f"No Samba share path in smb.conf matches remote root: {remote_root}", file=sys.stderr)
    sys.exit(1)

name, path = best
rel = posixpath.relpath(remote_root, path)
rel = "" if rel == "." else rel

def url_part(value: str) -> str:
    return value.strip("/").replace(" ", "%20")

share_url = f"//{server}/{url_part(name)}"
project_url = share_url + (f"/{url_part(rel)}" if rel else "")

values = {
    "SAMBA_SHARE_URL": share_url,
    "SAMBA_PROJECT_URL": project_url,
    "SAMBA_PROJECT_REL": rel,
    "SAMBA_SHARE_NAME": name,
    "SAMBA_SHARE_PATH": path,
}
for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
