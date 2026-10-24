---
name: remove
description: Remove the new-task-split hook's venv, model, config and logs. Use for "uninstall new-task-split", "remove the split hook".
---

Run `${CLAUDE_PLUGIN_ROOT}/scripts/ntsctl uninstall` (add `--keep-logs` if the user wants the decision log kept). The hook is now inert. To drop the hook registration itself, tell the user to run `/plugin uninstall new-task-split`.
