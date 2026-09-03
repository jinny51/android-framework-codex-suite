#!/usr/bin/env bash
set -euo pipefail
# 通过 SSH 读取远端服务器 /etc/samba/smb.conf，列出所有可用 Samba 共享。

usage() {
  cat <<'USAGE'
用法:
  discover-samba-share.sh --ssh-host <user@server|server> [选项]

选项:
  --ssh-host HOST       SSH 主机，用于读取远端 /etc/samba/smb.conf。必需。
  --server-name NAME    //server/share URL 中的主机名/IP。默认: ssh -G HostName。
  --smb-conf PATH       远端 Samba 配置文件路径。默认: /etc/samba/smb.conf。
  -h, --help            显示此帮助。

输出 (每个共享一个块，空行分隔):
  SHARE_NAME            共享段名，如 unisoc。
  SHARE_PATH            远端文件系统路径，如 /home/test61/unisoc。
  SHARE_URL             Samba URL，如 //192.168.100.23/unisoc。

退出码:
  0  成功
  2  缺少参数
  3  SSH 连接失败
  4  无法读取远端配置
USAGE
}

die() {
  local code="$1"; shift
  echo "ERROR: $*" >&2
  exit "$code"
}

ssh_host=; server_name=; smb_conf=/etc/samba/smb.conf

while [ "$#" -gt 0 ]; do
  case "$1" in
    --ssh-host)    ssh_host="${2:?缺少 --ssh-host 的值}"; shift 2 ;;
    --server-name) server_name="${2:?缺少 --server-name 的值}"; shift 2 ;;
    --smb-conf)    smb_conf="${2:?缺少 --smb-conf 的值}"; shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    *)             die 2 "未知参数: $1" ;;
  esac
done

[ -n "$ssh_host" ] || die 2 "--ssh-host 是必需的"

if [ -z "$server_name" ]; then
  server_name="$(ssh -G "$ssh_host" 2>/dev/null | awk '$1=="hostname"{print $2; exit}' || true)"
  [ -n "$server_name" ] || server_name="${ssh_host#*@}"
fi

# ── 读取远端 Samba 配置 ──
conf="$(ssh -o ConnectTimeout=8 "$ssh_host" "test -r '$smb_conf' && cat '$smb_conf'" 2>/dev/null)" || {
  die 4 "无法通过 SSH 读取远端 ${smb_conf}，请确认 SSH 用户有读取权限"
}

conf_file="$(mktemp)"
trap 'rm -f "$conf_file"' EXIT
printf "%s\n" "$conf" >"$conf_file"

# ── 解析共享 ──
python3 - "$server_name" "$conf_file" <<'PY'
import posixpath, re, shlex, sys

server, conf_path = sys.argv[1], sys.argv[2]
section = None

with open(conf_path, "r", encoding="utf-8", errors="ignore") as fh:
    lines = list(fh)

for raw in lines:
    line = raw.strip()
    if not line or line.startswith(("#", ";")):
        continue
    m = re.match(r"\[([^\]]+)\]", line)
    if m:
        section = m.group(1).strip()
        continue
    if section is None or section.lower() in {"global", "printers", "print$"}:
        continue
    pm = re.match(r"(?i)path\s*=\s*(.+)", line)
    if not pm:
        continue
    path = posixpath.normpath(pm.group(1).strip())
    if path:
        print(f"SHARE_NAME={shlex.quote(section)}")
        print(f"SHARE_PATH={shlex.quote(path)}")
        print(f"SHARE_URL={shlex.quote(f'//{server}/{section}')}")
        print()
PY
