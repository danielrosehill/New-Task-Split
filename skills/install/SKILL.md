---
name: install
description: Install the new-task-split hook's local model (venv + int8 ONNX from Hugging Face) and enable it. Use for "install new-task-split", "set up the split hook".
---

Run `${CLAUDE_PLUGIN_ROOT}/scripts/ntsctl install`, which leaves the hook disabled. Add `--enable --shadow` to log decisions without ever splitting, or just `--enable` for live splitting. Promoting from a `claudehook` trial: the model is already installed, so `ntsctl enable` (or `enable --shadow`) is all it takes. For a one-session trial instead, use the `trial` skill or run `${CLAUDE_PLUGIN_ROOT}/scripts/ntsctl launcher` to link `~/.local/bin/claudehook`; then `claudehook [--shadow]` starts a session with the hook on, and plain `claude` stays off.

Needs Python 3.10+ and network access to huggingface.co (~155 MB download). Uses `uv` if present, otherwise `python -m venv`. Report the smoke-test scores and the mode it ended in. Changes take effect on the next prompt.
