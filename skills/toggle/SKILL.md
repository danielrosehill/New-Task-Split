---
name: toggle
description: Enable, disable, switch shadow/split mode, set the threshold or context turns or show status of the new-task-split hook. Use for "turn off auto split", "enable split hook", "shadow mode", "split status".
---

`${CLAUDE_PLUGIN_ROOT}/scripts/ntsctl <cmd>`:

- `enable` / `enable --split` / `enable --shadow`: on; shadow logs only.
- `disable`: off; model kept.
- `status`: config, model revision and the last 10 decisions.
- `threshold 0.97` / `threshold default`: higher = fewer splits.
- `turns 1|2|3|4` / `turns default`: how many trailing exchanges are sent as context (default 4). For one session: `claudehook --turns N` or `NEW_TASK_SPLIT_TURNS=N`.

For one session only, the user can type `split off` / `split on`, or start Claude with `NEW_TASK_SPLIT=off`. Prefix a single prompt with `same:` to force continue or `new:` to force a split.
