#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
create-checkpoint.sh --ssh-host HOST --remote-root PATH [options]

Create a recoverable checkpoint under .codex/checkpoints using authoritative
remote repo/git state. This script does not git add or git commit.

Required:
  --ssh-host HOST        SSH host alias, hostname, or user@host.
  --remote-root PATH     Absolute source path on the remote build server.

Optional:
  --ssh-user USER        SSH user when HOST is not already user@host.
  --name NAME            Checkpoint name. Default: checkpoint-YYYYmmdd-HHMMSS.
  --purpose TEXT         Short reason written to metadata.
  --path PATH            Limit tracked git diff to path. Repeatable. Git-root mode only.
  --no-untracked         Do not archive untracked files.
  --dry-run              Check remote project mode and print intended checkpoint path.
  --output FILE          Save command summary to FILE.

Environment:
  SSHPASS                If set and sshpass exists, use it for SSH password auth.

For Android repo checkouts without a top-level git worktree, per-project patches
are packed into NAME.repo-patches.tgz with NAME.restore-repo-patches.sh.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

guard_output_path() {
  local output_path="$1"
  local plugin_lib
  plugin_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)/lib"
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$plugin_lib${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -m android_framework_ops.artifact_paths --purpose "checkpoint summary output" "$output_path" >/dev/null
}

sanitize_name() {
  local value="$1"
  value="${value:-checkpoint-$(date +%Y%m%d-%H%M%S)}"
  printf "%s" "$value" | sed -E 's/[^A-Za-z0-9._-]+/-/g; s/^-+//; s/-+$//'
}

SSH_HOST=""
SSH_USER=""
REMOTE_ROOT=""
NAME=""
PURPOSE=""
INCLUDE_UNTRACKED=true
DRY_RUN=false
OUTPUT=""
declare -a PATH_FILTERS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-host) SSH_HOST="${2:-}"; shift 2 ;;
    --ssh-user) SSH_USER="${2:-}"; shift 2 ;;
    --remote-root) REMOTE_ROOT="${2:-}"; shift 2 ;;
    --name) NAME="${2:-}"; shift 2 ;;
    --purpose) PURPOSE="${2:-}"; shift 2 ;;
    --path) PATH_FILTERS+=("${2:-}"); shift 2 ;;
    --no-untracked) INCLUDE_UNTRACKED=false; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --output) OUTPUT="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -n "$SSH_HOST" ]] || die "--ssh-host is required"
[[ -n "$REMOTE_ROOT" ]] || die "--remote-root is required"
[[ "$REMOTE_ROOT" == /* ]] || die "--remote-root must be absolute"
if [[ -n "$OUTPUT" ]]; then
  guard_output_path "$OUTPUT"
fi

NAME="$(sanitize_name "$NAME")"
[[ -n "$NAME" ]] || die "checkpoint name became empty after sanitizing"

SSH_TARGET="$SSH_HOST"
if [[ -n "$SSH_USER" && "$SSH_HOST" != *@* ]]; then
  SSH_TARGET="${SSH_USER}@${SSH_HOST}"
fi

ssh_cmd=(ssh -o BatchMode=no -o ConnectTimeout=8 "$SSH_TARGET" "bash -s" --)
if [[ -n "${SSHPASS:-}" ]] && command -v sshpass >/dev/null 2>&1; then
  ssh_cmd=(sshpass -e "${ssh_cmd[@]}")
fi

summary="$("${ssh_cmd[@]}" "$REMOTE_ROOT" "$NAME" "$PURPOSE" "$INCLUDE_UNTRACKED" "$DRY_RUN" \
    "${PATH_FILTERS[@]}" <<'REMOTE_SCRIPT'
set -euo pipefail

REMOTE_ROOT="$1"
NAME="$2"
PURPOSE="$3"
INCLUDE_UNTRACKED="$4"
DRY_RUN="$5"
shift 5
PATH_FILTERS=("$@")

cd "$REMOTE_ROOT"
mkdir -p .codex/checkpoints
PREFIX=".codex/checkpoints/$NAME"

if [[ "$DRY_RUN" == "true" ]]; then
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'CHECKPOINT_DRY_RUN name=%s mode=git prefix=%s\n' "$NAME" "$PREFIX"
    exit 0
  fi
  if [[ -d .repo ]] && command -v repo >/dev/null 2>&1; then
    printf 'CHECKPOINT_DRY_RUN name=%s mode=repo prefix=%s\n' "$NAME" "$PREFIX"
    exit 0
  fi
  echo "ERROR: neither git worktree nor Android repo checkout found at $REMOTE_ROOT" >&2
  exit 2
fi

write_meta() {
  local mode="$1"
  local branch=""
  local head=""
  branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  head="$(git rev-parse HEAD 2>/dev/null || true)"
  {
    printf 'name=%s\n' "$NAME"
    printf 'created_at=%s\n' "$(date '+%F %T %z')"
    printf 'remote_root=%s\n' "$REMOTE_ROOT"
    printf 'mode=%s\n' "$mode"
    [[ -n "$branch" ]] && printf 'branch=%s\n' "$branch"
    [[ -n "$head" ]] && printf 'head=%s\n' "$head"
    [[ -n "$PURPOSE" ]] && printf 'purpose=%s\n' "$PURPOSE"
    if ((${#PATH_FILTERS[@]})); then
      printf 'path_filters=%s\n' "${PATH_FILTERS[*]}"
    fi
    if [[ "$mode" == "git" ]]; then
      printf 'restore_tracked=git apply .codex/checkpoints/%s.patch\n' "$NAME"
    else
      printf 'restore_tracked=bash .codex/checkpoints/%s.restore-repo-patches.sh <repo-root>\n' "$NAME"
    fi
    printf 'restore_untracked=tar -xzf .codex/checkpoints/%s.untracked-files.tgz -C <repo-root>\n' "$NAME"
  } >"$PREFIX.meta.txt"
}

archive_untracked_from_list() {
  local list_file="$1"
  if [[ "$INCLUDE_UNTRACKED" != "true" || ! -s "$list_file" ]]; then
    return 0
  fi
  grep -Ev '^(out|\.repo|\.git|\.codex)(/|$)' "$list_file" >"$PREFIX.untracked-files.txt" || true
  if [[ -s "$PREFIX.untracked-files.txt" ]]; then
    tar -czf "$PREFIX.untracked-files.tgz" -T "$PREFIX.untracked-files.txt"
  else
    rm -f "$PREFIX.untracked-files.txt"
  fi
}

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  write_meta "git"
  if ((${#PATH_FILTERS[@]})); then
    git status --short -- "${PATH_FILTERS[@]}" >"$PREFIX.status.txt"
    git diff --stat -- "${PATH_FILTERS[@]}" >"$PREFIX.stat.txt"
    git diff --binary -- "${PATH_FILTERS[@]}" >"$PREFIX.patch"
    git ls-files --others --exclude-standard -- "${PATH_FILTERS[@]}" >"$PREFIX.untracked-candidates.txt"
  else
    git status --short >"$PREFIX.status.txt"
    git diff --stat >"$PREFIX.stat.txt"
    git diff --binary >"$PREFIX.patch"
    git ls-files --others --exclude-standard >"$PREFIX.untracked-candidates.txt"
  fi
  archive_untracked_from_list "$PREFIX.untracked-candidates.txt"
  rm -f "$PREFIX.untracked-candidates.txt"
  printf 'CHECKPOINT_OK name=%s mode=git prefix=%s\n' "$NAME" "$PREFIX"
  exit 0
fi

if [[ -d .repo ]] && command -v repo >/dev/null 2>&1; then
  write_meta "repo"
  repo status >"$PREFIX.status.txt" || true
  repo diff >"$PREFIX.repo.diff" || true
  repo forall -c '
    stat="$(git diff --stat || true)"
    if [ -n "$stat" ]; then
      printf "### %s\n%s\n" "$REPO_PATH" "$stat"
    fi
  ' >"$PREFIX.stat.txt" || true

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT
  patches_dir="$tmp_dir/project-patches"
  mkdir -p "$patches_dir"
  export CHECKPOINT_PATCHES_DIR="$patches_dir"
  repo forall -c '
    if git diff --quiet && [ -z "$(git ls-files --others --exclude-standard)" ]; then
      exit 0
    fi
    safe="$(printf "%s" "${REPO_PATH:-root}" | sed -E "s#[^A-Za-z0-9._-]+#_#g")"
    mkdir -p "$CHECKPOINT_PATCHES_DIR/$safe"
    printf "%s\t%s\n" "$safe" "$REPO_PATH" >>"$CHECKPOINT_PATCHES_DIR/manifest.tsv"
    git diff --binary >"$CHECKPOINT_PATCHES_DIR/$safe/tracked.patch"
    git status --short >"$CHECKPOINT_PATCHES_DIR/$safe/status.txt"
    git diff --stat >"$CHECKPOINT_PATCHES_DIR/$safe/stat.txt"
  ' || true
  if [[ -s "$patches_dir/manifest.tsv" ]]; then
    tar -czf "$PREFIX.repo-patches.tgz" -C "$tmp_dir" project-patches
  fi

  cat >"$PREFIX.restore-repo-patches.sh" <<EOF_RESTORE
#!/usr/bin/env bash
set -euo pipefail
ROOT="\${1:-.}"
ARCHIVE="\$ROOT/.codex/checkpoints/$NAME.repo-patches.tgz"
[[ -f "\$ARCHIVE" ]] || { echo "missing archive: \$ARCHIVE" >&2; exit 2; }
TMP="\$(mktemp -d)"
trap 'rm -rf "\$TMP"' EXIT
tar -xzf "\$ARCHIVE" -C "\$TMP"
while IFS=\$'\t' read -r safe path; do
  patch="\$TMP/project-patches/\$safe/tracked.patch"
  [[ -s "\$patch" ]] || continue
  (cd "\$ROOT/\$path" && git apply "\$patch")
done < "\$TMP/project-patches/manifest.tsv"
EOF_RESTORE
  chmod +x "$PREFIX.restore-repo-patches.sh"

  repo forall -c '
    prefix="$REPO_PATH"
    [ "$prefix" = "." ] && prefix=""
    git ls-files --others --exclude-standard | while IFS= read -r f; do
      [ -n "$prefix" ] && printf "%s/%s\n" "$prefix" "$f" || printf "%s\n" "$f"
    done
  ' >"$PREFIX.untracked-candidates.txt" || true
  archive_untracked_from_list "$PREFIX.untracked-candidates.txt"
  rm -f "$PREFIX.untracked-candidates.txt"

  printf 'CHECKPOINT_OK name=%s mode=repo prefix=%s\n' "$NAME" "$PREFIX"
  exit 0
fi

echo "ERROR: neither git worktree nor Android repo checkout found at $REMOTE_ROOT" >&2
exit 2
REMOTE_SCRIPT
)"

if [[ -n "$OUTPUT" ]]; then
  printf "%s\n" "$summary" >"$OUTPUT"
fi
printf "%s\n" "$summary"
