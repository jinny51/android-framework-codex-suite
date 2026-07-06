#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
record-verification-recipe.sh --repo PATH --profile NAME [options]

Record or update a project-local verification recipe for a build profile.

Required:
  --repo PATH              Local WSL/Samba repo path.
  --profile NAME           Build profile name.

Optional:
  --needs-reboot BOOL      true, false, or auto.
  --logcat PATTERN         Key logcat pattern. Repeatable.
  --verify FLOW            Verification flow name. Repeatable.
  --notes TEXT             Short notes.
  --print                  Print the current stored recipe after update.

Output file:
  .codex/verification-recipes.sh

The script only updates project-local .codex memory. It does not run adb,
git, or builds.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

single_quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

REPO=""
PROFILE=""
NEEDS_REBOOT=""
NOTES=""
PRINT=false
LOGCATS=()
VERIFIES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO="${2:-}"; shift 2 ;;
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --needs-reboot) NEEDS_REBOOT="${2:-}"; shift 2 ;;
    --logcat) LOGCATS+=("${2:-}"); shift 2 ;;
    --verify) VERIFIES+=("${2:-}"); shift 2 ;;
    --notes) NOTES="${2:-}"; shift 2 ;;
    --print) PRINT=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -n "$REPO" ]] || die "--repo is required"
[[ -d "$REPO" ]] || die "repo path does not exist: $REPO"
[[ -n "$PROFILE" ]] || die "--profile is required"

case "${NEEDS_REBOOT:-auto}" in
  true|false|auto) ;;
  *) die "--needs-reboot must be true, false, or auto" ;;
esac

CODEX_DIR="$REPO/.codex"
RECIPES_FILE="$CODEX_DIR/verification-recipes.sh"
mkdir -p "$CODEX_DIR"

declare -A VERIFY_NEEDS_REBOOT=()
declare -A VERIFY_LOGCAT_PATTERNS=()
declare -A VERIFY_FLOWS=()
declare -A VERIFY_NOTES=()
declare -A VERIFY_UPDATED_AT=()

if [[ -f "$RECIPES_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$RECIPES_FILE"
fi

join_lines() {
  local IFS="|"
  printf "%s" "$*"
}

if [[ -n "$NEEDS_REBOOT" ]]; then
  VERIFY_NEEDS_REBOOT[$PROFILE]="$NEEDS_REBOOT"
elif [[ -z "${VERIFY_NEEDS_REBOOT[$PROFILE]:-}" ]]; then
  VERIFY_NEEDS_REBOOT[$PROFILE]="auto"
fi
if ((${#LOGCATS[@]})); then
  VERIFY_LOGCAT_PATTERNS[$PROFILE]="$(join_lines "${LOGCATS[@]}")"
fi
if ((${#VERIFIES[@]})); then
  VERIFY_FLOWS[$PROFILE]="$(join_lines "${VERIFIES[@]}")"
fi
if [[ -n "$NOTES" ]]; then
  VERIFY_NOTES[$PROFILE]="$NOTES"
fi
VERIFY_UPDATED_AT[$PROFILE]="$(date '+%F %T %z')"

write_array() {
  local array_name="$1"
  local key
  echo "declare -A $array_name=()"
  while IFS= read -r key; do
    [[ -n "$key" ]] || continue
    local value
    value="$(eval "printf '%s' \"\${${array_name}[\$key]}\"")"
    printf "%s[%s]=%s\n" "$array_name" "$(single_quote "$key")" "$(single_quote "$value")"
  done < <(eval "printf '%s\n' \"\${!${array_name}[@]}\"" | sort)
}

tmp="$(mktemp)"
{
  echo "#!/usr/bin/env bash"
  echo "# Project-local verification recipe memory."
  write_array VERIFY_NEEDS_REBOOT
  write_array VERIFY_LOGCAT_PATTERNS
  write_array VERIFY_FLOWS
  write_array VERIFY_NOTES
  write_array VERIFY_UPDATED_AT
} >"$tmp"
mv "$tmp" "$RECIPES_FILE"
chmod +x "$RECIPES_FILE"

echo "VERIFY_RECIPE_OK profile=$PROFILE file=$RECIPES_FILE"
if [[ "$PRINT" == true ]]; then
  echo "VERIFY_RECIPE profile=$PROFILE needs_reboot=${VERIFY_NEEDS_REBOOT[$PROFILE]:-auto} logcat=${VERIFY_LOGCAT_PATTERNS[$PROFILE]:-} flows=${VERIFY_FLOWS[$PROFILE]:-} notes=${VERIFY_NOTES[$PROFILE]:-}"
fi
