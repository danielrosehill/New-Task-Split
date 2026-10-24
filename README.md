# New-Task-Split

**Status: prototype (v0.1, 2026-10-24).** A Claude Code plugin that notices when the user drops an
unrelated task into a long session and moves that prompt into a fresh session (`/clear`, then re-send)
automatically, so each task keeps a clean context.

Each prompt is scored locally by a small int8 ONNX cross-encoder,
[`danielrosehill/Agent-Task-Break-Detector-ModernBERT`](https://huggingface.co/danielrosehill/Agent-Task-Break-Detector-ModernBERT)
(ModernBERT-base, trained on the synthetic
[Agent-Task-Break-Detector](https://huggingface.co/datasets/danielrosehill/Agent-Task-Break-Detector) dataset).
It does no per-turn API calls. The input is the new prompt plus the last 4 exchanges.

## Quick trial: `claudehook` (one session only)

The repo can be used without installing the plugin:

```bash
git clone https://github.com/danielrosehill/New-Task-Split
New-Task-Split/scripts/ntsctl launcher      # links ~/.local/bin/claudehook
claudehook             # Claude Code with auto-split ON for this session only
claudehook --shadow    # ON, but log only (ntsctl status shows what it would have split)
claudehook --turns 2   # this session sends only the last 2 exchanges as context
```

`claudehook` passes any other arguments through to `claude`. On first run it installs the model, which is left disabled. It then loads
the plugin with `claude --plugin-dir` and sets `NEW_TASK_SPLIT=split|shadow` for that process alone, so a
plain `claude` session never runs the hook. If the plugin is already installed, `claudehook` only sets the env var.
`ntsctl launcher --remove` removes the link. Inside Claude Code, the `trial` skill does the same setup.

**Promote** a trial to always on with `ntsctl enable` (or `--shadow`), or the `install` skill. **Demote** with `ntsctl disable`; `claudehook` still works while the hook is disabled.

## Setup (always available)

```
/plugin marketplace add danielrosehill/Claude-Code-Plugins
/plugin install new-task-split@danielrosehill
```

Then ask Claude to "install new-task-split" (skill `install`), or run the following directly:

```bash
~/.claude/plugins/.../new-task-split/scripts/ntsctl install --enable --shadow
```

`install` creates a venv (`onnxruntime`, `tokenizers`, `numpy`; it uses `uv` if present), downloads
the int8 model (~155 MB, sha256-checked against the Hub), runs a smoke test. The hook stays **disabled** unless the user passes
`--enable` (with `--shadow` for log-only mode).

Requirements: Python 3.10+ and Linux or macOS.

The hook is registered as soon as the plugin is installed, but it does nothing until `ntsctl install` has run and the
config says `enabled`.

## Enable / disable

| Command | Effect |
|---|---|
| `ntsctl enable --shadow` | On, **log only**: decisions go to the log, nothing is split. Start here. |
| `ntsctl enable --split` | On, and splits for real. |
| `ntsctl disable` | Off. The venv and model are kept. |
| `ntsctl status` | Config, model revision, last 10 decisions. |
| `ntsctl threshold 0.97` / `default` | Raise or lower the bar for a split (higher means fewer splits). |
| `ntsctl turns 1\|2\|3\|4` / `default` | How many trailing exchanges the model sees (default 4). |

Settings take effect on the next prompt. There is no need to restart. The `toggle` skill wraps these commands.

Per session, typed as a whole prompt:

- `split off` / `split on`: pause or resume for this session.
- `NEW_TASK_SPLIT=off claude`: off for that process. `NEW_TASK_SPLIT=split` or `shadow` turns it on for that
  process whatever the config says. This is what `claudehook` sets.

Per prompt:

- `same: …` keeps the prompt in this session.
- `new: …` forces a split.

## Context window

The model sees the new prompt plus the last **N exchanges** (one exchange is a prompt and the agent's reply),
newest first. Each exchange is cut to the last 600 characters of the reply and the first 600 of the
prompt, and the whole input is capped at 512 tokens, with the oldest exchange dropped first.

N is 1–4 and defaults to 4, which is what the model was trained on.

- Set it with `ntsctl turns N`, or `NEW_TASK_SPLIT_TURNS=N`, or `claudehook --turns N` for one session.
- A smaller N reacts only to the most recent exchanges.
- A larger N gives more sense of the session's topic.
- More than 4 is not offered, because the current model never saw it.
- Each logged decision records the `turns` it used, so shadow logs from different settings can be compared.

## What a split looks like

The hook blocks the prompt and, in a background helper, types `/clear` and then the prompt back into the
same terminal. The fresh session is told that it was auto-split.

**Undo:** run `/resume`, pick the previous session and re-send. A prompt re-sent within 30 minutes is never
split again.

Terminal transport:

- tmux (`send-keys`).
- Konsole (D-Bus).
- Anywhere else, the prompt is copied to the clipboard (`wl-copy`, `xclip` or `pbcopy`) and the user
  is asked to `/clear` and paste.

It fails open: any error, a missing model or a disabled config lets the prompt through untouched.

Prompts shorter than 40 characters, and sessions with fewer than 2 earlier prompts, are never split.

## Update the model

`ntsctl update-model` fetches the newest Hub revision. `ntsctl update-model --revision <sha>` pins one.

- The previous model is kept in `model.prev/`.
- The model's recommended threshold (from `new_task_split.json` in the model repo) is applied unless
  a manual override is set.

## Remove

`ntsctl uninstall` deletes the venv, model, config and logs; `--keep-logs` keeps the decision log.
To remove the hook registration as well, run `/plugin uninstall new-task-split`.

## Files

- `~/.local/share/new-task-split/` (`$NEW_TASK_SPLIT_HOME`): venv, model, `config.json`.
- `~/.cache/new-task-split/` (`$NEW_TASK_SPLIT_STATE`): `decisions.jsonl` and per-session state.

## Limitations

- **Synthetic training data only.** The model has not yet been checked against real sessions.
- **Run shadow mode first.** Use `ntsctl status` to see what it would have split.
- **Threshold 0.76** (int8, calibrated 2026-10-24 on the synthetic validation split). On the test split this gives
  precision 0.94 and recall 0.89. Real-session precision is unknown.
- **Latency:** about 1.5 s per prompt on CPU, because the model is loaded on every call.
- **English only.**

## Licence

MIT (plugin). Model Apache-2.0, dataset CC BY 4.0.
