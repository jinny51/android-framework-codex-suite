#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
用法:
  migrate-state-dir.sh [--from PATH] [--to PATH] [--dry-run]

用途:
  一次性把旧 android-macos-source-access 本地状态目录迁移到 ~/.servers。
  运行脚本不会再读取旧 ~/.codex/android-macos-source-access-info；如果旧目录仍有内容，
  请显式执行本迁移脚本完成移动。

默认:
  --from ~/.codex/android-macos-source-access-info
  --to   ~/.servers

输出:
  MIGRATION_STATUS=migrated|not_needed|dry_run
  MOVED=<relative path>

退出码:
  0  成功或无需迁移
  2  参数错误
  3  目标路径存在同名文件，拒绝覆盖
USAGE
}

die() {
  local code="$1"
  shift
  echo "ERROR: $*" >&2
  exit "$code"
}

old_dir="${HOME}/.codex/android-macos-source-access-info"
new_dir="${HOME}/.servers"
dry_run=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --from) old_dir="${2:?缺少 --from 的值}"; shift 2 ;;
    --to) new_dir="${2:?缺少 --to 的值}"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die 2 "未知参数: $1" ;;
  esac
done

if [ ! -d "$old_dir" ]; then
  echo "MIGRATION_STATUS=not_needed"
  echo "OLD_DIR=$old_dir"
  echo "NEW_DIR=$new_dir"
  exit 0
fi

moved=0
for name in credentials projects; do
  src="$old_dir/$name"
  dst="$new_dir/$name"
  [ -e "$src" ] || continue
  if [ -e "$dst" ] && [ -n "$(find "$src" -mindepth 1 -maxdepth 1 2>/dev/null)" ]; then
    for item in "$src"/*; do
      [ -e "$item" ] || continue
      base="$(basename "$item")"
      [ ! -e "$dst/$base" ] || die 3 "目标已存在，拒绝覆盖: $dst/$base"
    done
  fi
done

if [ "$dry_run" -eq 1 ]; then
  echo "MIGRATION_STATUS=dry_run"
  echo "OLD_DIR=$old_dir"
  echo "NEW_DIR=$new_dir"
  find "$old_dir" -mindepth 1 -maxdepth 2 -print | sed "s#^$old_dir/#MOVED=#"
  exit 0
fi

mkdir -p "$new_dir"
chmod 700 "$new_dir"

for name in credentials projects; do
  src="$old_dir/$name"
  dst="$new_dir/$name"
  [ -e "$src" ] || continue
  mkdir -p "$dst"
  chmod 700 "$dst"
  shopt -s nullglob dotglob
  for item in "$src"/*; do
    base="$(basename "$item")"
    mv "$item" "$dst/$base"
    echo "MOVED=$name/$base"
    moved=$((moved + 1))
  done
  shopt -u nullglob dotglob
  rmdir "$src" 2>/dev/null || true
done

rmdir "$old_dir" 2>/dev/null || true
rmdir "$(dirname "$old_dir")" 2>/dev/null || true

echo "MIGRATION_STATUS=migrated"
echo "OLD_DIR=$old_dir"
echo "NEW_DIR=$new_dir"
echo "MOVED_COUNT=$moved"
