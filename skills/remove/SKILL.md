---
name: remove
description: Remove the new-task-split hook's venv, model, config and logs. Use for "uninstall new-task-split", "remove the split hook".
---

Run `${CLAUDE_PLUGIN_ROOT}/scripts/ntsctl uninstall` (add `--keep-logs` if the user wants the decision log kept). This also removes the `~/.local/bin/claudehook` launcher link. To end only a trial, keeping the model, run `ntsctl launcher --remove` instead. The hook is now inert. To drop the hook registration itself, tell the user to run `/plugin uninstall new-task-split`.
