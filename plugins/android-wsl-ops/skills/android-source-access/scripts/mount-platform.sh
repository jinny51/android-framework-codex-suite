#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  mount-platform.sh --platform <unisoc|mtk|rk> --share //<server>/<share> [options]

Options:
  --platform NAME        Platform folder name. Without --target, defaults to $ANDROID_WORK_ROOT/NAME or $HOME/work/NAME.
  --share URL           Samba/CIFS URL, for example //server/TVA10A2R or //server/work/rk/TVA10A2R.
  --user USER           Samba username. Omit only for anonymous/guest mounts.
  --target PATH         Explicit mount target. Project-level callers should pass this.
  --mount-root PATH     Default: $ANDROID_WORK_ROOT or $HOME/work.
  --credentials PATH    Existing mount.cifs credentials file.
  --password-env NAME   Environment variable containing the Samba password. Default: SAMBA_PASSWORD.
  --sudo-password-env NAME
                       Environment variable containing local WSL sudo password.
  --guest               Mount without username/password.
  --dry-run             Print the mount command shape without executing it.
  -h, --help            Show this help.

Password handling:
  Prefer SAMBA_PASSWORD or --password-env. The script writes a temporary credentials
  file with mode 600 and removes it on exit. It does not persist secrets.
USAGE
}

platform=
share=
user=
target=
target_explicit=0
mount_root="${ANDROID_WORK_ROOT:-$HOME/work}"
credentials=
password_env=SAMBA_PASSWORD
sudo_password_env=
guest=0
dry_run=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --platform) platform="${2:?missing value for --platform}"; shift 2 ;;
    --share) share="${2:?missing value for --share}"; shift 2 ;;
    --user) user="${2:?missing value for --user}"; shift 2 ;;
    --target) target="${2:?missing value for --target}"; target_explicit=1; shift 2 ;;
    --mount-root) mount_root="${2:?missing value for --mount-root}"; shift 2 ;;
    --credentials) credentials="${2:?missing value for --credentials}"; shift 2 ;;
    --password-env) password_env="${2:?missing value for --password-env}"; shift 2 ;;
    --sudo-password-env) sudo_password_env="${2:?missing value for --sudo-password-env}"; shift 2 ;;
    --guest) guest=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$platform" ] || { echo "--platform is required" >&2; exit 2; }
[ -n "$share" ] || { echo "--share is required" >&2; exit 2; }

if [ -z "$target" ]; then
  target="${mount_root%/}/$platform"
fi

case "$share" in
  //*) ;;
  *) echo "--share must look like //<server>/<share>" >&2; exit 2 ;;
esac

share_body="${share#//}"
if [ "$target_explicit" -eq 0 ] && [[ "$share_body" == */*/* ]]; then
  echo "--share includes a subpath: $share" >&2
  echo "Without --target this helper mounts to a platform folder, so pass a share root such as //server/share." >&2
  echo "For project-level mounts, pass --target and use the exact project URL." >&2
  exit 2
fi

if ! command -v mount.cifs >/dev/null 2>&1; then
  echo "mount.cifs is not installed or not on PATH" >&2
  exit 1
fi

if mountpoint -q "$target"; then
  existing_source="$(findmnt -n -o SOURCE --mountpoint "$target" 2>/dev/null || true)"
  if [ "$existing_source" = "$share" ]; then
    echo "$target is already mounted from $share"
    findmnt --mountpoint "$target"
    exit 0
  fi
  echo "$target is already mounted from $existing_source, not $share" >&2
  echo "Refusing to replace an existing mount without an explicit unmount request." >&2
  exit 1
fi

if [ -e "$target" ] && [ ! -d "$target" ]; then
  echo "Target exists but is not a directory: $target" >&2
  exit 1
fi

if [ -d "$target" ] && [ -n "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  echo "Target directory is non-empty and not a mount point: $target" >&2
  echo "Refusing to hide existing files under a CIFS mount." >&2
  exit 1
fi

uid="$(id -u)"
gid="$(id -g)"
opts=(
  "vers=3.0"
  "cache=strict"
  "uid=$uid"
  "forceuid"
  "gid=$gid"
  "forcegid"
  "file_mode=0644"
  "dir_mode=0755"
  "soft"
  "nounix"
  "noperm"
  "actimeo=1"
)

temp_credentials=
cleanup() {
  if [ -n "$temp_credentials" ] && [ -f "$temp_credentials" ]; then
    rm -f "$temp_credentials"
  fi
}
trap cleanup EXIT

if [ "$dry_run" -eq 1 ]; then
  if [ "$guest" -eq 1 ]; then
    opts+=("guest")
  elif [ -n "$credentials" ]; then
    opts+=("credentials=$credentials")
  else
    [ -n "$user" ] || { echo "--user is required unless --guest or --credentials is used" >&2; exit 2; }
    opts+=("credentials=<temporary-from-$password_env>")
  fi
elif [ "$guest" -eq 1 ]; then
  opts+=("guest")
elif [ -n "$credentials" ]; then
  [ -f "$credentials" ] || { echo "credentials file not found: $credentials" >&2; exit 2; }
  opts+=("credentials=$credentials")
else
  [ -n "$user" ] || { echo "--user is required unless --guest or --credentials is used" >&2; exit 2; }
  password="${!password_env-}"
  if [ -z "$password" ]; then
    echo "Password env $password_env is empty. Export it or pass --credentials." >&2
    exit 2
  fi
  temp_credentials="$(mktemp)"
  chmod 600 "$temp_credentials"
  {
    printf 'username=%s\n' "$user"
    printf 'password=%s\n' "$password"
  } > "$temp_credentials"
  opts+=("credentials=$temp_credentials")
fi

opts_csv="$(IFS=,; echo "${opts[*]}")"

sudo_mode=
sudo_password=
if [ -n "$sudo_password_env" ]; then
  sudo_password="${!sudo_password_env-}"
fi

prepare_sudo() {
  if sudo -n true 2>/dev/null; then
    sudo_mode=nopass
  elif [ -n "$sudo_password" ] && printf '%s\n' "$sudo_password" | sudo -S -p '' true 2>/dev/null; then
    sudo_mode=password
  else
    echo "LOCAL_SUDO_REQUIRED action=mount_cifs" >&2
    exit 5
  fi
}

sudo_run() {
  if [ "$sudo_mode" = nopass ]; then
    sudo -n "$@"
  else
    printf '%s\n' "$sudo_password" | sudo -S -p '' "$@"
  fi
}

if [ "$dry_run" -eq 1 ]; then
  echo "sudo mkdir -p '$target'"
  echo "sudo mount -t cifs '$share' '$target' -o '<template opts with credentials hidden>'"
  echo "effective non-secret opts: $opts_csv"
  exit 0
fi

prepare_sudo
echo "LOCAL_SUDO_AUTH mode=$sudo_mode"
sudo_run mkdir -p "$target"
sudo_run mount -t cifs "$share" "$target" -o "$opts_csv"
if [ -n "$temp_credentials" ]; then
  echo "SAMBA_AUTH mode=password"
elif [ -n "$credentials" ]; then
  echo "SAMBA_AUTH mode=credentials"
elif [ "$guest" -eq 1 ]; then
  echo "SAMBA_AUTH mode=guest"
fi
findmnt --mountpoint "$target"
