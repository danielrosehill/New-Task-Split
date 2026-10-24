---
name: update-model
description: Update the new-task-split classifier to the newest (or a pinned) Hugging Face revision. Use for "update the split model", "new model version".
---

Run `${CLAUDE_PLUGIN_ROOT}/scripts/ntsctl update-model` (or `--revision <sha>` to pin). It verifies sha256 against the Hub, keeps the previous model in `model.prev/`, re-runs the smoke test and applies the model's recommended threshold unless the user has an override. Report the old and new revision.
