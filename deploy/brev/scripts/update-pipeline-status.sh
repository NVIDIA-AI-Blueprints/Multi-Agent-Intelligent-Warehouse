#!/usr/bin/env bash
set -euo pipefail

repo_root="${MAIW_ROOT:-/maiw}"
brev_dir="${repo_root}/deploy/brev"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
entity_dir="${brev_dir}/generated/entities"
state_dir="${brev_dir}/generated/setup-state"
entity_file="${entity_dir}/pipeline-status.yaml"
data_marker="${state_dir}/data-installed-at"
user_marker="${state_dir}/user-created-at"

mkdir -p "$entity_dir" "$state_dir"
chmod 0755 "$entity_dir" "$state_dir" 2>/dev/null || true

yaml_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

yaml_block() {
  local key="$1"
  local value="$2"

  printf '  %s: |-\n' "$key"
  if [ -n "$value" ]; then
    printf '%s\n' "$value" | sed 's/^/    /'
  else
    printf '    \n'
  fi
}

step_status() {
  case "$1" in
    0)
      printf 'complete'
      ;;
    2)
      printf 'starting'
      ;;
    *)
      printf 'stopped'
      ;;
  esac
}

step_icon() {
  case "$1" in
    0)
      printf '🟢'
      ;;
    2)
      printf '⚪'
      ;;
    *)
      printf '🔴'
      ;;
  esac
}

marker_value() {
  local marker="$1"

  if [ -s "$marker" ]; then
    head -n 1 "$marker"
  fi
}

is_at_or_after() {
  local candidate="$1"
  local reference="$2"

  [ -n "$candidate" ] || return 1
  [ -n "$reference" ] || return 1
  [ "$candidate" = "$reference" ] || [[ "$candidate" > "$reference" ]]
}

set +e
configured_output="$(MAIW_ROOT="$repo_root" "$script_dir/status.sh" 2>&1)"
configured_code="$?"
set -e
configured_output="${configured_output:-NVIDIA API key status unavailable}"
configured_detail="$configured_output"

set +e
container_output="$(MAIW_ROOT="$repo_root" "$script_dir/container-status.sh" --allow-health-starting 2>&1)"
running_code="$?"
set -e
container_output="${container_output:-Container status unavailable}"
case "$running_code" in
  0)
    running_detail="All blueprint containers are running"
    ;;
  2)
    running_detail="Blueprint containers are starting"
    ;;
  *)
    running_detail="Blueprint containers are stopped"
    ;;
esac
if [ -n "$container_output" ]; then
  running_detail="${running_detail}: ${container_output//$'\n'/; }"
fi

data_installed=false
data_detail="Demo data has not been installed"
data_installed_at="$(marker_value "$data_marker")"
if [ -n "$data_installed_at" ]; then
  data_installed=true
  data_detail="Demo data installed at ${data_installed_at}"
fi

user_created=false
user_detail="Account passwords need to be set after demo data install"
user_created_at="$(marker_value "$user_marker")"
if is_at_or_after "$user_created_at" "$data_installed_at"; then
  user_created=true
  user_detail="Account passwords set at ${user_created_at}"
fi

tmp_file="$(mktemp)"
{
  printf -- '- name: "setup_pipeline"\n'
  printf '  is_configured: %s\n' "$([ "$configured_code" -eq 0 ] && printf true || printf false)"
  printf '  is_running: %s\n' "$([ "$running_code" -eq 0 ] && printf true || printf false)"
  printf '  data_is_installed: %s\n' "$data_installed"
  printf '  user_is_created: %s\n' "$user_created"
  printf '  configure_status: "%s"\n' "$(step_status "$configured_code")"
  printf '  running_status: "%s"\n' "$(step_status "$running_code")"
  printf '  data_status: "%s"\n' "$(step_status "$([ "$data_installed" = true ] && printf 0 || printf 1)")"
  printf '  user_status: "%s"\n' "$(step_status "$([ "$user_created" = true ] && printf 0 || printf 1)")"
  printf '  configure_action: "configure-blueprint"\n'
  printf '  running_action: "Start%%20Blueprint"\n'
  printf '  data_action: "Install%%20Demo%%20Data"\n'
  printf '  user_action: "Set%%20Account%%20Passwords"\n'
  printf '  configure_display: "Configure"\n'
  printf '  running_display: "Start"\n'
  printf '  data_display: "Install Demo Data"\n'
  printf '  user_display: "Reset Passwords"\n'
  printf '  configure_detail: "%s"\n' "$(yaml_escape "$configured_detail")"
  printf '  running_detail: "%s"\n' "$(yaml_escape "$running_detail")"
  printf '  data_detail: "%s"\n' "$(yaml_escape "$data_detail")"
  printf '  user_detail: "%s"\n' "$(yaml_escape "$user_detail")"
  yaml_block "configure_output" "$configured_output"
  yaml_block "running_output" "$container_output"
} > "$tmp_file"
chmod 0644 "$tmp_file"
mv "$tmp_file" "$entity_file"

printf 'Pipeline: '
printf '%s Configure  ' "$(step_icon "$configured_code")"
printf '%s Start  ' "$(step_icon "$running_code")"
printf '%s Install Demo Data  ' "$(step_icon "$([ "$data_installed" = true ] && printf 0 || printf 1)")"
printf '%s Reset Passwords\n' "$(step_icon "$([ "$user_created" = true ] && printf 0 || printf 1)")"

printf '\n'
printf '%s Configure - %s\n' "$(step_icon "$configured_code")" "$configured_detail"
printf '%s Start - %s\n' "$(step_icon "$running_code")" "$running_detail"
printf '%s Install Demo Data - %s\n' "$(step_icon "$([ "$data_installed" = true ] && printf 0 || printf 1)")" "$data_detail"
printf '%s Reset Passwords - %s\n' "$(step_icon "$([ "$user_created" = true ] && printf 0 || printf 1)")" "$user_detail"
