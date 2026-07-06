#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ensure-samba-share.sh --ssh-host HOST --remote-root /home/<user>/<sdk-root> [options]

Check whether the remote SDK path is covered by Samba config. If it is not,
print the share that should be added. With --apply, append the share to
/etc/samba/smb.conf, validate it, and reload/restart Samba.

Default share plan:
  /home/test55/work/unisoc/rk3576 -> [rk3576] path = /home/test55/work/unisoc/rk3576

Normal first-time mounting should pass the source-inspected SDK/project name:
  --share-name TVA10A2R --share-path /home/test55/work/unisoc/rk3576

Parent/platform shares are explicit exceptions. To create one, pass both
--share-name and --share-path for the intended parent directory.

Options:
  --ssh-host HOST       SSH host/alias used to read or update smb.conf. Required.
  --remote-root PATH    Remote SDK root path. Required.
  --share-name NAME     Override Samba share name. Default: remote root basename.
  --share-path PATH     Override Samba share path. Default: remote root.
  --smb-conf PATH       Samba config path. Default: /etc/samba/smb.conf.
  --sudo-password-env NAME
                       Environment variable containing remote sudo password.
  --apply               Modify the remote Samba config. Default is check-only.
  -h, --help            Show this help.

Notes:
  --apply requires remote sudo access, either passwordless or via --sudo-password-env.
  The script backs up smb.conf, validates with testparm when available, and
  restores the backup if validation fails.
USAGE
}

ssh_host=
remote_root=
share_name=
share_path=
share_name_explicit=0
share_path_explicit=0
smb_conf=/etc/samba/smb.conf
sudo_password_env=
apply=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ssh-host) ssh_host="${2:?missing value for --ssh-host}"; shift 2 ;;
    --remote-root) remote_root="${2:?missing value for --remote-root}"; shift 2 ;;
    --share-name) share_name="${2:?missing value for --share-name}"; share_name_explicit=1; shift 2 ;;
    --share-path) share_path="${2:?missing value for --share-path}"; share_path_explicit=1; shift 2 ;;
    --smb-conf) smb_conf="${2:?missing value for --smb-conf}"; shift 2 ;;
    --sudo-password-env) sudo_password_env="${2:?missing value for --sudo-password-env}"; shift 2 ;;
    --apply) apply=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$ssh_host" ] || { echo "--ssh-host is required" >&2; exit 2; }
[ -n "$remote_root" ] || { echo "--remote-root is required" >&2; exit 2; }

case "$remote_root" in
  /home/*/*) ;;
  *)
    echo "remote root must look like /home/<user>/<sdk-root>: $remote_root" >&2
    exit 2
    ;;
esac

trimmed="${remote_root#/home/}"
remote_user="${trimmed%%/*}"
remote_basename="${remote_root%/}"
remote_basename="${remote_basename##*/}"
share_name="${share_name:-$remote_basename}"
share_path="${share_path:-$remote_root}"

remote_check='
set -euo pipefail
remote_root="$1"
share_path="$2"
smb_conf="$3"

test -d "$remote_root" || { echo "REMOTE_PATH_MISSING path=$remote_root" >&2; exit 3; }
test -d "$share_path" || { echo "SHARE_PATH_MISSING path=$share_path" >&2; exit 3; }
test -r "$smb_conf" || { echo "SMB_CONF_UNREADABLE path=$smb_conf" >&2; exit 4; }
cat "$smb_conf"
'

conf="$(ssh "$ssh_host" "bash -s -- $(printf '%q' "$remote_root") $(printf '%q' "$share_path") $(printf '%q' "$smb_conf")" <<<"$remote_check")"
conf_file="$(mktemp)"
trap 'rm -f "$conf_file"' EXIT
printf "%s\n" "$conf" >"$conf_file"

if python3 - "$remote_root" "$conf_file" <<'PY'
import posixpath
import re
import sys

remote_root, conf_path = sys.argv[1], sys.argv[2]
remote_root = posixpath.normpath(remote_root)
section = None
shares = []

with open(conf_path, "r", encoding="utf-8", errors="ignore") as fh:
    for raw in fh:
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
        if path_match:
            path = posixpath.normpath(path_match.group(1).strip())
            shares.append((section, path))

for name, path in shares:
    if remote_root == path or remote_root.startswith(path.rstrip("/") + "/"):
        print(f"SAMBA_SHARE_OK share={name} path={path}")
        sys.exit(0)

sys.exit(1)
PY
then
  exit 0
fi

requested_share_name="$share_name"
share_name="$(python3 - "$requested_share_name" "$remote_user" "$conf_file" <<'PY'
import re
import sys

requested, remote_user, conf_path = sys.argv[1], sys.argv[2], sys.argv[3]
sections = set()
with open(conf_path, "r", encoding="utf-8", errors="ignore") as fh:
    for raw in fh:
        match = re.match(r"\s*\[([^\]]+)\]", raw)
        if match:
            sections.add(match.group(1).strip())

if requested not in sections:
    print(requested)
    sys.exit(0)

base = f"{requested}_{remote_user}"
candidate = base
index = 2
while candidate in sections:
    candidate = f"{base}_{index}"
    index += 1
print(candidate)
PY
)"
if [ "$share_name" != "$requested_share_name" ]; then
  echo "SAMBA_SHARE_NAME_CONFLICT requested=$requested_share_name using=$share_name"
fi

echo "SAMBA_CONFIG_NEEDED share=$share_name path=$share_path remote_root=$remote_root"
if [ "$apply" -ne 1 ]; then
  exit 1
fi

remote_apply='
set -euo pipefail
share_name="$1"
share_path="$2"
valid_user="$3"
smb_conf="$4"
sudo_password=""
sudo_mode=""

if [ "${CODEX_SUDO_PASSWORD_STDIN:-0}" = "1" ]; then
  IFS= read -r sudo_password || true
fi

if sudo -n true 2>/dev/null; then
  sudo_mode=nopass
elif [ -n "$sudo_password" ] && printf "%s\n" "$sudo_password" | sudo -S -p "" true 2>/dev/null; then
  sudo_mode=password
else
  echo "REMOTE_SUDO_REQUIRED host=$(hostname) action=edit_smb_conf" >&2
  exit 5
fi
echo "REMOTE_SUDO_AUTH mode=$sudo_mode"

sudo_run() {
  if [ "$sudo_mode" = nopass ]; then
    sudo -n "$@"
  else
    printf "%s\n" "$sudo_password" | sudo -S -p "" "$@"
  fi
}

test -d "$share_path" || { echo "SHARE_PATH_MISSING path=$share_path" >&2; exit 3; }

backup="${smb_conf}.codex-$(date +%Y%m%d-%H%M%S).bak"
sudo_run cp "$smb_conf" "$backup"
tmp="$(mktemp)"
trap "rm -f \"$tmp\"" EXIT

cat >"$tmp" <<EOF

[$share_name]
    path = $share_path
    browseable = yes
    read only = no
    valid users = $valid_user
    create mask = 0644
    directory mask = 0755
EOF

sudo_run sh -c "cat \"\$1\" >> \"\$2\"" sh "$tmp" "$smb_conf"

if command -v testparm >/dev/null 2>&1; then
  if ! sudo_run testparm -s "$smb_conf" >/dev/null; then
    sudo_run cp "$backup" "$smb_conf"
    echo "SMB_CONF_INVALID restored_backup=$backup" >&2
    exit 6
  fi
fi

reloaded=false
if command -v systemctl >/dev/null 2>&1; then
  for svc in smbd smb samba; do
    if sudo_run systemctl reload "$svc" 2>/dev/null || sudo_run systemctl restart "$svc" 2>/dev/null; then
      reloaded=true
      break
    fi
  done
fi
if [ "$reloaded" = false ] && command -v service >/dev/null 2>&1; then
  for svc in smbd smb samba; do
    if sudo_run service "$svc" reload 2>/dev/null || sudo_run service "$svc" restart 2>/dev/null; then
      reloaded=true
      break
    fi
  done
fi
if [ "$reloaded" = false ]; then
  sudo_run cp "$backup" "$smb_conf"
  echo "SAMBA_RELOAD_FAILED restored_backup=$backup" >&2
  exit 7
fi

echo "SAMBA_CONFIG_OK share=$share_name path=$share_path backup=$backup"
'

remote_tmp="$(ssh "$ssh_host" 'mktemp /tmp/codex-ensure-samba.XXXXXX')"
cleanup_remote() {
  ssh "$ssh_host" "rm -f $(printf '%q' "$remote_tmp")" >/dev/null 2>&1 || true
}
trap 'rm -f "$conf_file"; cleanup_remote' EXIT
ssh "$ssh_host" "cat > $(printf '%q' "$remote_tmp") && chmod 700 $(printf '%q' "$remote_tmp")" <<<"$remote_apply"

sudo_password=""
if [ -n "$sudo_password_env" ]; then
  sudo_password="${!sudo_password_env-}"
fi

remote_cmd="$(printf '%q' "$remote_tmp") $(printf '%q' "$share_name") $(printf '%q' "$share_path") $(printf '%q' "$remote_user") $(printf '%q' "$smb_conf")"
if [ -n "$sudo_password" ]; then
  printf "%s\n" "$sudo_password" | ssh "$ssh_host" "CODEX_SUDO_PASSWORD_STDIN=1 $remote_cmd"
else
  ssh "$ssh_host" "$remote_cmd"
fi
