#!/bin/sh
# Hook entry point. Runs the hook with the plugin's own venv; until `ntsctl install` has created
# it, does nothing, so an uninstalled or half-installed plugin never blocks a prompt.
home="${NEW_TASK_SPLIT_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/new-task-split}"
py="$home/venv/bin/python"
[ -x "$py" ] || exit 0
exec "$py" "$(dirname "$0")/new_task_split.py" "$@"
