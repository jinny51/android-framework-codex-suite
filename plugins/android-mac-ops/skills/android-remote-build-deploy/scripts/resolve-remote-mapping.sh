#!/usr/bin/env bash
set -euo pipefail
# 从 android-macos-source-access 的 JSON registry 解析 SSH_HOST 和 REMOTE_ROOT。

usage() {
  cat <<'USAGE'
用法:
  resolve-remote-mapping.sh --project /本地/项目/路径 [选项]

选项:
  --project PATH       本地项目路径。必需。
  --registry-dir PATH  Registry 目录。默认: ~/.codex/android-macos-source-access-info/projects。
  -h, --help           显示此帮助。

输出:
  SSH_HOST, REMOTE_ROOT, PLATFORM, SDK_NAME, MAPPING_REGISTRY

退出码:
  0  找到映射
  1  未找到映射
  2  缺少参数
USAGE
}

die() { local c="$1"; shift; echo "ERROR: $*" >&2; exit "$c"; }

project_path=; registry_dir="${HOME}/.codex/android-macos-source-access-info/projects"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --project)      project_path="${2:?缺少 --project 的值}"; shift 2 ;;
    --registry-dir) registry_dir="${2:?缺少 --registry-dir 的值}"; shift 2 ;;
    -h|--help)      usage; exit 0 ;;
    *)              die 2 "未知参数: $1" ;;
  esac
done

[ -n "$project_path" ] || die 2 "--project 是必需的"
[ -d "$registry_dir" ] || die 1 "registry 目录不存在: $registry_dir"

for reg_file in "$registry_dir"/*.json; do
  [ -f "$reg_file" ] || continue

  result="$(python3 - "$reg_file" "$project_path" <<'PY'
import json, sys
reg_file, target = sys.argv[1], sys.argv[2]
with open(reg_file) as fh:
    data = json.load(fh)
for share_info in data.get("shares", {}).values():
    for proj_name, proj_info in share_info.get("projects", {}).items():
        lp = proj_info.get("local_path", "").rstrip("/")
        if lp == target or lp == target.rstrip("/"):
            print(f"SSH_HOST={data.get('server','')}")
            print(f"REMOTE_ROOT={proj_info.get('remote_path','')}")
            p = proj_info.get("platform",""); [p] and print(f"PLATFORM={p}")
            print(f"SDK_NAME={proj_name}")
            print(f"MAPPING_REGISTRY={reg_file}")
            sys.exit(0)
sys.exit(1)
PY
)"
  [ $? -eq 0 ] && { echo "$result"; exit 0; }
done

die 1 "未找到项目映射: ${project_path}（请先执行 android-macos-source-access 的 mount + register）"
