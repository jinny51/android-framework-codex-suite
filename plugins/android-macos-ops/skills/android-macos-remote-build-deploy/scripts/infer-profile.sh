#!/usr/bin/env bash
set -euo pipefail
# 根据变更的源码路径推断构建 profile 和模块。

usage() {
  cat <<'USAGE'
用法:
  infer-profile.sh --repo PATH --path FILE [--path FILE ...]

选项:
  --repo PATH           本地项目路径。必需。
  --path FILE           变更的文件路径。可重复。必需。
  --from-file FILE      从文件读取路径列表（- 为 stdin）。
  -h, --help            显示此帮助。

输出:
  PROFILE, MODULES, ARTIFACTS, CONFIDENCE

退出码:
  0  成功
  2  缺少参数
USAGE
}

die() { local c="$1"; shift; echo "ERROR: $*" >&2; exit "$c"; }

repo=; paths=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo)      repo="${2:?缺少 --repo 的值}"; shift 2 ;;
    --path)      paths+=("${2:?缺少 --path 的值}"); shift 2 ;;
    --from-file)
      while IFS= read -r p; do [ -n "$p" ] && paths+=("$p"); done < "${2:?缺少 --from-file 的值}"
      shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *)           die 2 "未知参数: $1" ;;
  esac
done

[ -n "$repo" ] || die 2 "--repo 是必需的"
[ ${#paths[@]} -gt 0 ] || die 2 "至少需要一个 --path"

modules=(); artifacts=(); profile=""; confidence=0

for p in "${paths[@]}"; do
  case "$p" in
    */services/core/*|*/services/java/*)
      profile="services"; modules+=("services"); artifacts+=("system/framework/services.jar"); confidence=$((confidence+1)) ;;
    */base/core/*|*/base/services/*)
      profile="framework"; modules+=("framework"); artifacts+=("system/framework/framework.jar"); confidence=$((confidence+1)) ;;
    */SystemUI/*|*/SystemUIGoogle/*)
      profile="systemui"; modules+=("SystemUI"); artifacts+=("system/priv-app/SystemUI/SystemUI.apk"); confidence=$((confidence+1)) ;;
    */Settings/*)
      profile="settings"; modules+=("Settings"); artifacts+=("system/priv-app/Settings/Settings.apk"); confidence=$((confidence+1)) ;;
    */Launcher3/*|*/Launcher/*)
      profile="launcher"; modules+=("Launcher3"); artifacts+=("system/priv-app/Launcher3/Launcher3.apk"); confidence=$((confidence+1)) ;;
    *)
      [[ "$p" == */services/* ]] && { modules+=("services"); artifacts+=("system/framework/services.jar"); confidence=$((confidence+1)); }
      [[ "$p" == */base/* ]]     && { modules+=("framework"); artifacts+=("system/framework/framework.jar"); confidence=$((confidence+1)); }
      ;;
  esac
done

modules=($(printf '%s\n' "${modules[@]}" | sort -u))
artifacts=($(printf '%s\n' "${artifacts[@]}" | sort -u))

if [ ${#modules[@]} -gt 0 ]; then
  echo "PROFILE=${profile:-auto}"
  echo "MODULES=$(IFS=,; echo "${modules[*]}")"
  echo "ARTIFACTS=$(IFS=,; echo "${artifacts[*]}")"
  echo "CONFIDENCE=$confidence"
else
  echo "PROFILE=unknown"
  echo "MODULES="
  echo "ARTIFACTS="
  echo "CONFIDENCE=0"
fi
