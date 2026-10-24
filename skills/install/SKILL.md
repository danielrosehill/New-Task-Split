---
name: install
description: Install the new-task-split hook's local model (venv + int8 ONNX from Hugging Face) and enable it. Use for "install new-task-split", "set up the split hook".
---

Run `${CLAUDE_PLUGIN_ROOT}/scripts/ntsctl install --shadow` unless the user asked for live splitting, in which case drop `--shadow`. Shadow mode logs decisions but never splits; recommend it for the first few days.

Needs Python 3.10+ and network access to huggingface.co (~155 MB download). Uses `uv` if present, otherwise `python -m venv`. Report the smoke-test scores and the mode it ended in. Changes take effect on the next prompt.
