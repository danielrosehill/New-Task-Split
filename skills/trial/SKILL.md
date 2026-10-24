---
name: trial
description: Set up the `claudehook` test launcher, which starts one Claude Code session with new-task-split on while plain `claude` stays off. Use for "try new-task-split", "set up the test CLI", "test the split hook".
---

Set up a one-session trial without enabling the hook anywhere else.

1. Run `${CLAUDE_PLUGIN_ROOT}/scripts/ntsctl install` if `ntsctl status` shows `"model_installed": false`. This downloads about 155 MB and leaves the hook disabled.
2. Run `${CLAUDE_PLUGIN_ROOT}/scripts/ntsctl launcher`. This links `~/.local/bin/claudehook`. If `~/.local/bin` is not on `PATH`, give the user the full path instead.
3. Tell the user how to start a trial:
   - `claudehook --shadow` turns the hook on but only logs decisions. Suggest this first.
   - `claudehook` turns it on and splits for real. A split needs tmux or Konsole; anywhere else the prompt goes to the clipboard.
   - `--turns 1|2|3|4` sets how many trailing exchanges the model sees, for this session only.
   - Any other arguments go through to `claude`.
4. To review a trial, run `ntsctl status`. It shows the last 10 decisions with `p_new_task`. If it splits too often, raise the threshold with `ntsctl threshold 0.85`; if too rarely, lower it.

How it works: the launcher runs `claude --plugin-dir <plugin root>` and sets `NEW_TASK_SPLIT=split|shadow` for that process only. If the plugin is already installed, it only sets the env var.

- **Promote to always on:** use the `install` skill (`ntsctl enable [--shadow]`). `claudehook` keeps working after that.
- **End the trial:** run `ntsctl launcher --remove`. The `remove` skill also unlinks the launcher.
