#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
install-ssh-key.sh --ssh-host HOST [options]

Install an existing local SSH public key on the remote account so later
discovery/build commands can use SSH without a password.

Options:
  --ssh-host HOST       SSH host alias, hostname, or user@host.
  --ssh-user USER       SSH user when HOST is not already user@host.
  --public-key PATH     Public key to install. Default: ~/.ssh/id_ed25519.pub, then ~/.ssh/id_rsa.pub.
  --password-env NAME   Environment variable containing the SSH password. Default: SSHPASS.
  --generate-key        Generate ~/.ssh/id_ed25519 if no public key exists.
  --dry-run             Print what would be done.
  -h, --help            Show this help.

Environment:
  SSHPASS               SSH password when key install requires password auth.

The script does not store passwords.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

SSH_HOST=""
SSH_USER=""
PUBLIC_KEY=""
PASSWORD_ENV="SSHPASS"
GENERATE_KEY=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-host) SSH_HOST="${2:-}"; shift 2 ;;
    --ssh-user) SSH_USER="${2:-}"; shift 2 ;;
    --public-key) PUBLIC_KEY="${2:-}"; shift 2 ;;
    --password-env) PASSWORD_ENV="${2:-}"; shift 2 ;;
    --generate-key) GENERATE_KEY=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -n "$SSH_HOST" ]] || die "--ssh-host is required"

SSH_TARGET="$SSH_HOST"
if [[ -n "$SSH_USER" && "$SSH_HOST" != *@* ]]; then
  SSH_TARGET="${SSH_USER}@${SSH_HOST}"
fi

if [[ -z "$PUBLIC_KEY" ]]; then
  for candidate in "$HOME/.ssh/id_ed25519.pub" "$HOME/.ssh/id_rsa.pub"; do
    if [[ -f "$candidate" ]]; then
      PUBLIC_KEY="$candidate"
      break
    fi
  done
fi

if [[ -z "$PUBLIC_KEY" && "$GENERATE_KEY" == true ]]; then
  PRIVATE_KEY="$HOME/.ssh/id_ed25519"
  if [[ "$DRY_RUN" == true ]]; then
    echo "WOULD_GENERATE_KEY $PRIVATE_KEY"
  else
    mkdir -p "$HOME/.ssh"
    chmod 700 "$HOME/.ssh"
    ssh-keygen -t ed25519 -N "" -f "$PRIVATE_KEY" -C "codex-android-source-access@$(hostname)" >/dev/null
  fi
  PUBLIC_KEY="$PRIVATE_KEY.pub"
fi

[[ -n "$PUBLIC_KEY" ]] || die "no public key found; create one or rerun with --generate-key"
if [[ ! -f "$PUBLIC_KEY" ]]; then
  if [[ "$DRY_RUN" == true && "$GENERATE_KEY" == true ]]; then
    :
  else
    die "public key not found: $PUBLIC_KEY"
  fi
fi

if [[ "$DRY_RUN" == true ]]; then
  echo "WOULD_CHECK_KEY ssh -o BatchMode=yes $SSH_TARGET true"
  echo "WOULD_INSTALL_KEY $PUBLIC_KEY -> $SSH_TARGET"
  exit 0
fi

if ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_TARGET" true >/dev/null 2>&1; then
  echo "SSH_KEY_OK target=$SSH_TARGET"
  exit 0
fi

password="${!PASSWORD_ENV-}"

if command -v ssh-copy-id >/dev/null 2>&1; then
  if [[ -n "$password" ]] && command -v sshpass >/dev/null 2>&1; then
    env SSHPASS="$password" sshpass -e ssh-copy-id -i "$PUBLIC_KEY" "$SSH_TARGET" >/dev/null
  elif [[ -t 0 ]]; then
    ssh-copy-id -i "$PUBLIC_KEY" "$SSH_TARGET"
  else
    die "password auth is needed but sshpass is unavailable or $PASSWORD_ENV is empty; install sshpass, set $PASSWORD_ENV, or run ssh-copy-id manually"
  fi
else
  [[ -n "$password" ]] || die "ssh-copy-id is unavailable and $PASSWORD_ENV is empty"
  command -v sshpass >/dev/null 2>&1 || die "ssh-copy-id and sshpass are unavailable; install one or add the key manually"
  pub_line="$(sed -n '1p' "$PUBLIC_KEY")"
  remote_cmd='mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && grep -qxF "$PUB_LINE" ~/.ssh/authorized_keys || printf "%s\n" "$PUB_LINE" >> ~/.ssh/authorized_keys'
  env SSHPASS="$password" sshpass -e ssh "$SSH_TARGET" "PUB_LINE=$(printf "%q" "$pub_line") bash -lc $(printf "%q" "$remote_cmd")"
fi

if ssh -o BatchMode=yes -o ConnectTimeout=8 "$SSH_TARGET" true >/dev/null 2>&1; then
  echo "SSH_KEY_INSTALLED target=$SSH_TARGET key=$PUBLIC_KEY"
else
  die "key install finished but passwordless SSH verification failed: $SSH_TARGET"
fi
