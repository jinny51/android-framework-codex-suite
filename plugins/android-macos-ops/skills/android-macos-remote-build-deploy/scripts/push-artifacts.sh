#!/usr/bin/env bash
set -euo pipefail
# 通过本地 adb 推送构建产物到已连接的 Android 设备。

usage() {
  cat <<'USAGE'
用法:
  push-artifacts.sh --artifact PATH --dest PATH [选项]

选项:
  --artifact PATH       要推送的产物。可重复。
  --dest PATH            设备端目标路径。与 --artifact 一一对应。
  --product-out PATH     用于推断目标路径的 product out 目录。
  --adb-serial SERIAL    adb 设备序列号。
  --reboot               推送后重启。
  --wait-boot            重启后等待启动完成。
  --dry-run              仅打印操作，不执行。
  -h, --help             显示此帮助。

环境变量:
  ADB                    adb 命令路径。默认: adb。

退出码:
  0  成功
  2  缺少参数
  3  产物文件不存在
  4  无 adb 设备
USAGE
}

die() { local c="$1"; shift; echo "ERROR: $*" >&2; exit "$c"; }

artifacts=(); dests=(); product_out=; adb_serial=
reboot=false; wait_boot=false; dry_run=false
adb="${ADB:-adb}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --artifact)    artifacts+=("${2:?缺少 --artifact 的值}"); shift 2 ;;
    --dest)        dests+=("${2:?缺少 --dest 的值}"); shift 2 ;;
    --product-out) product_out="${2:?缺少 --product-out 的值}"; shift 2 ;;
    --adb-serial)  adb_serial="${2:?缺少 --adb-serial 的值}"; shift 2 ;;
    --reboot)      reboot=true; shift ;;
    --wait-boot)   wait_boot=true; shift ;;
    --dry-run)     dry_run=true; shift ;;
    -h|--help)     usage; exit 0 ;;
    *)             die 2 "未知参数: $1" ;;
  esac
done

[ ${#artifacts[@]} -gt 0 ] || die 2 "至少需要一个 --artifact"

# 从 product_out 推断目标路径
if [ ${#dests[@]} -eq 0 ] && [ -n "$product_out" ]; then
  for a in "${artifacts[@]}"; do
    case "$a" in
      */system/*)  d="${a#*/system/}"; dests+=("/system/$d") ;;
      */vendor/*)  d="${a#*/vendor/}"; dests+=("/vendor/$d") ;;
      */product/*) d="${a#*/product/}"; dests+=("/product/$d") ;;
      *)           dests+=("/system/framework/") ;;
    esac
  done
fi

[ ${#artifacts[@]} -eq ${#dests[@]} ] || die 2 "产物数量(${#artifacts[@]})与目标数量(${#dests[@]})不匹配"

# dry-run 模式
if [ "$dry_run" = true ]; then
  for i in "${!artifacts[@]}"; do
    echo "DRY_RUN: adb push ${artifacts[$i]} ${dests[$i]}"
  done
  [ "$reboot" = true ] && echo "DRY_RUN: adb reboot"
  echo "PUSH_STATUS=dry_run_ok"
  exit 0
fi

adb_cmd="$adb"
[ -n "$adb_serial" ] && adb_cmd="$adb -s $adb_serial"

# 检查设备
$adb_cmd wait-for-device 2>/dev/null || die 4 "无 adb 设备，请连接设备后重试"
$adb_cmd root 2>/dev/null || true
$adb_cmd remount 2>/dev/null || true

for i in "${!artifacts[@]}"; do
  src="${artifacts[$i]}"; dst="${dests[$i]}"
  [ -f "$src" ] || die 3 "产物文件不存在: $src"
  echo "PUSH: $src -> $dst"
  $adb_cmd push "$src" "$dst"
done

if [ "$reboot" = true ]; then
  echo "REBOOT: 设备重启中..."
  $adb_cmd reboot
  [ "$wait_boot" = true ] && { $adb_cmd wait-for-device; echo "BOOT_COMPLETE"; }
fi

echo "PUSH_STATUS=ok"
