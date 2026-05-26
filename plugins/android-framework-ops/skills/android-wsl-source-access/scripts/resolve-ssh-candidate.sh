#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  resolve-ssh-candidate.sh --remote-root /home/<user>/... [options]

Resolve likely SSH targets for an Android remote source path.
Do not guess DNS hostnames. Use explicit IP or SSH config HostName values.

Options:
  --remote-root PATH     Remote SDK root path. Required.
  --ip IP               Prefer this IP and emit <remote-user>@IP first.
  --ssh-config PATH     Extra OpenSSH config to scan. Default: Windows VSCode config when present.
  --connect-timeout N   Seconds for quick SSH/TCP checks. Default: 3.
  -h, --help            Show this help.

Output:
  Shell-style KEY=VALUE lines:
    SSH_HOST            Best candidate SSH target.
    SERVER_NAME         Host/IP for Samba URLs.
    SSH_READY           1 when passwordless SSH and remote path are already usable.
    SSH_CANDIDATES      Array of candidate SSH targets, ordered best first.
    SERVER_NAMES        Array parallel to SSH_CANDIDATES.
USAGE
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

remote_root=
ip=
ssh_config=
connect_timeout=3

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote-root) remote_root="${2:-}"; shift 2 ;;
    --ip) ip="${2:-}"; shift 2 ;;
    --ssh-config) ssh_config="${2:-}"; shift 2 ;;
    --connect-timeout) connect_timeout="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ -n "$remote_root" ]] || die "--remote-root is required"
case "$remote_root" in
  /home/*/*) ;;
  *) die "remote root must look like /home/<user>/..." ;;
esac

trimmed="${remote_root#/home/}"
remote_user="${trimmed%%/*}"

if [[ -z "$ssh_config" ]]; then
  for candidate in \
    "/mnt/c/Users/$USER/.ssh/config" \
    "/mnt/c/Users/$(whoami)/.ssh/config"; do
    if [[ -f "$candidate" ]]; then
      ssh_config="$candidate"
      break
    fi
  done
fi

declare -a targets=()
declare -a servers=()
declare -a labels=()

add_candidate() {
  local target="$1"
  local server="$2"
  local label="$3"
  local existing
  [[ -n "$target" && -n "$server" ]] || return 0
  for existing in "${targets[@]:-}"; do
    [[ "$existing" == "$target" ]] && return 0
  done
  targets+=("$target")
  servers+=("$server")
  labels+=("$label")
}

ssh_g_value() {
  local host="$1"
  local key="$2"
  ssh -G "$host" 2>/dev/null | awk -v k="$key" '$1 == k {print $2; exit}' || true
}

if [[ -n "$ip" ]]; then
  add_candidate "$remote_user@$ip" "$ip" "explicit_ip"
fi

g_hostname="$(ssh_g_value "$remote_user" hostname)"
g_user="$(ssh_g_value "$remote_user" user)"
if [[ -n "$g_hostname" && "$g_hostname" != "$remote_user" && "$g_user" == "$remote_user" ]]; then
  add_candidate "$remote_user@$g_hostname" "$g_hostname" "wsl_ssh_config_user"
fi

if [[ -n "$ssh_config" && -f "$ssh_config" ]]; then
  # The /home/<user>/... segment is most reliably the remote login user.
  # Prefer config entries whose User matches it, then keep Host-name matches as a fallback.
  while IFS=$'\t' read -r host hostname user; do
    [[ -n "$host" && -n "$hostname" ]] || continue
    [[ "$user" == "$remote_user" ]] || continue
    add_candidate "$remote_user@$hostname" "$hostname" "ssh_config_user:$host"
  done < <(
    awk -v key="$remote_user" '
      BEGIN { IGNORECASE=1 }
      function emit() {
        if (host != "" && hostname != "") {
          printf "%s\t%s\t%s\n", host, hostname, user
        }
      }
      $1 == "Host" { emit(); host=$2; hostname=""; user=""; next }
      $1 == "HostName" { hostname=$2; next }
      $1 == "User" { user=$2; next }
      END { emit() }
    ' "$ssh_config"
  )

  while IFS=$'\t' read -r host hostname user; do
    [[ -n "$host" && -n "$hostname" ]] || continue
    [[ "$host" == "$remote_user" ]] || continue
    add_candidate "${user:-$remote_user}@$hostname" "$hostname" "ssh_config_host:$host"
  done < <(
    awk '
      BEGIN { IGNORECASE=1 }
      function emit() {
        if (host != "" && hostname != "") {
          printf "%s\t%s\t%s\n", host, hostname, user
        }
      }
      $1 == "Host" { emit(); host=$2; hostname=""; user=""; next }
      $1 == "HostName" { hostname=$2; next }
      $1 == "User" { user=$2; next }
      END { emit() }
    ' "$ssh_config"
  )
fi

if [[ -n "$g_hostname" && "$g_hostname" != "$remote_user" ]]; then
  add_candidate "${g_user:-$remote_user}@$g_hostname" "$g_hostname" "wsl_ssh_config_host"
fi

check_ssh_ready() {
  local target="$1"
  ssh -o BatchMode=yes -o ConnectTimeout="$connect_timeout" "$target" \
    "test -d $(printf '%q' "$remote_root")" >/dev/null 2>&1
}

check_port_open() {
  local server="$1"
  timeout "$connect_timeout" bash -c "</dev/tcp/$server/22" >/dev/null 2>&1
}

declare -a ready_targets=()
declare -a ready_servers=()
declare -a ready_labels=()
declare -a open_targets=()
declare -a open_servers=()
declare -a open_labels=()
declare -a rest_targets=()
declare -a rest_servers=()
declare -a rest_labels=()

for i in "${!targets[@]}"; do
  if check_ssh_ready "${targets[$i]}"; then
    ready_targets+=("${targets[$i]}")
    ready_servers+=("${servers[$i]}")
    ready_labels+=("${labels[$i]}")
  elif check_port_open "${servers[$i]}"; then
    open_targets+=("${targets[$i]}")
    open_servers+=("${servers[$i]}")
    open_labels+=("${labels[$i]}")
  else
    rest_targets+=("${targets[$i]}")
    rest_servers+=("${servers[$i]}")
    rest_labels+=("${labels[$i]}")
  fi
done

targets=("${ready_targets[@]}" "${open_targets[@]}" "${rest_targets[@]}")
servers=("${ready_servers[@]}" "${open_servers[@]}" "${rest_servers[@]}")
labels=("${ready_labels[@]}" "${open_labels[@]}" "${rest_labels[@]}")

print_array_assignment() {
  local name="$1"
  shift
  printf "%s=(" "$name"
  local value
  for value in "$@"; do
    printf " %q" "$value"
  done
  printf " )\n"
}

if [[ "${#targets[@]}" -eq 0 ]]; then
  echo "IP_REQUIRED remote_user=$remote_user reason=no_ssh_config_candidate" >&2
  echo "Provide the server IP, for example: ip192.168.0.199" >&2
  exit 2
fi

ssh_ready=0
if [[ "${#ready_targets[@]}" -gt 0 && "${targets[0]}" == "${ready_targets[0]}" ]]; then
  ssh_ready=1
fi

printf "REMOTE_USER=%q\n" "$remote_user"
printf "SSH_HOST=%q\n" "${targets[0]}"
printf "SERVER_NAME=%q\n" "${servers[0]}"
printf "SSH_READY=%q\n" "$ssh_ready"
if [[ -n "$ssh_config" && -f "$ssh_config" ]]; then
  printf "SSH_CONFIG_USED=%q\n" "$ssh_config"
else
  printf "SSH_CONFIG_USED=%q\n" ""
fi
print_array_assignment SSH_CANDIDATES "${targets[@]}"
print_array_assignment SERVER_NAMES "${servers[@]}"
print_array_assignment CANDIDATE_LABELS "${labels[@]}"
