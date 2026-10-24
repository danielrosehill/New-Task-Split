#!/usr/bin/env python3
"""new-task-split: move a prompt that starts an unrelated task into a fresh Claude Code session.

One script, three entry points:

  UserPromptSubmit hook   score the prompt with the local model; on "new task" block it here and
                          re-send it after /clear into the same terminal
  SessionStart hook       (source=clear) tell the fresh session it was auto-split, and how to undo
  --dispatch              detached helper that types "/clear" and the prompt into the terminal

The classifier is a local int8 ONNX cross-encoder (ModernBERT-base fine-tuned on the
Agent-Task-Break-Detector dataset), installed by `ntsctl install`. No network call per turn.

Claude Code hooks cannot run /clear or swap sessions, so the terminal itself is driven: tmux
send-keys, or Konsole over D-Bus. Anything else falls back to copying the prompt to the clipboard
and asking the user to /clear and paste.

Fails open: any error, a missing model or a disabled config means the prompt goes through untouched.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ntsconfig  # noqa: E402

STATE = ntsconfig.STATE
MIN_PRIOR_PROMPTS = 2      # a session this young has no context worth protecting
MIN_PROMPT_CHARS = 40      # "yes", "push it", "looks good" are always continuations
RETURN_WINDOW = 30 * 60    # a split prompt re-sent within this many seconds is an undo
KEEP_PREFIXES = ("same:", "here:")
FORCE_PREFIXES = ("new:", "split:")
MAX_TURNS = 4              # as in training: the last 4 exchanges, newest first
TURN_CHARS = 600           # agent turns in training were short summaries; keep the tail of real ones


# ---------- state ----------

def _state_file(session_id: str) -> Path:
    return STATE / "sessions" / f"{session_id}.json"


def load_state(session_id: str) -> dict:
    try:
        return json.loads(_state_file(session_id).read_text())
    except (OSError, ValueError):
        return {}


def save_state(session_id: str, state: dict) -> None:
    path = _state_file(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def log(record: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with open(STATE / "decisions.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(" ".join(prompt.split()).encode()).hexdigest()[:16]


def split_just_now(session_id: str, window: float = 20.0) -> bool:
    """Loop guard: this session handed a message off moments ago, so don't split again."""
    try:
        last = json.loads((STATE / "splits.jsonl").read_text().splitlines()[-1])
    except (OSError, ValueError, IndexError):
        return False
    return last.get("from") == session_id and time.time() - last["t"] < window


def recently_split(h: str, session_id: str) -> bool:
    """True if this exact prompt was auto-split out of this session recently: the user brought it
    back (undo), so it belongs here. The fresh session receiving the moved copy doesn't match."""
    try:
        lines = (STATE / "splits.jsonl").read_text().splitlines()
    except OSError:
        return False
    now = time.time()
    for line in reversed(lines[-200:]):
        rec = json.loads(line)
        if rec["hash"] == h and rec.get("from") == session_id and now - rec["t"] < RETURN_WINDOW:
            return True
    return False


# ---------- transcript ----------

def read_exchanges(transcript_path: str) -> list[dict]:
    """Return [{user, agent}] for the prompts typed so far, each with the agent's last text reply
    to it. Tool calls, tool results and meta lines are skipped."""
    exchanges: list[dict] = []
    try:
        lines = Path(transcript_path).read_text().splitlines()
    except OSError:
        return exchanges
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("isMeta") or entry.get("isSidechain"):
            continue
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") == "user":
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
            else:
                continue
            if text.strip() and not text.lstrip().startswith("<"):
                exchanges.append({"user": text, "agent": ""})
        elif entry.get("type") == "assistant" and isinstance(content, list) and exchanges:
            text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
            if text.strip():
                exchanges[-1]["agent"] = text
    return exchanges


# ---------- classifier ----------

def format_context(exchanges: list[dict]) -> str:
    """Same layout as training (Agent-Context-Harness model/common.py fmt_pair)."""
    turns = exchanges[-MAX_TURNS:][::-1]
    return "\n".join(f"AGENT: {t['agent'][-TURN_CHARS:]}\nUSER: {t['user'][:TURN_CHARS]}" for t in turns)


def score(message: str, exchanges: list[dict], model_dir: Path) -> float:
    """p(new_task) from the local int8 ONNX model."""
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
    tok.no_padding()
    tok.enable_truncation(512, strategy="only_second")
    enc = tok.encode(message, format_context(exchanges))
    so = ort.SessionOptions()
    so.intra_op_num_threads = int(os.environ.get("NEW_TASK_SPLIT_THREADS", "4"))
    sess = ort.InferenceSession(str(model_dir / "model_int8.onnx"), so, providers=["CPUExecutionProvider"])
    logits = sess.run(None, {"input_ids": np.array([enc.ids], dtype=np.int64),
                             "attention_mask": np.array([enc.attention_mask], dtype=np.int64)})[0][0]
    z = np.exp(logits - logits.max())
    return float(z[1] / z.sum())


# ---------- terminal transport ----------

def _ancestors() -> set[int]:
    """PIDs of this process and its ancestors (Linux /proc). Empty if unavailable."""
    pids, pid = set(), os.getpid()
    try:
        while pid > 1:
            pids.add(pid)
            pid = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return set()
    return pids


def _qdbus() -> str | None:
    # Plain `qdbus` is often the Qt5 chooser stub and fails on Qt6-only KDE installs.
    return next((q for q in ("qdbus6", "/usr/lib/qt6/bin/qdbus", "qdbus") if shutil.which(q)), None)


def _target_pid(kind: str) -> int | None:
    try:
        if kind == "tmux":
            out = subprocess.run(["tmux", "display-message", "-p", "-t", os.environ["TMUX_PANE"], "#{pane_pid}"],
                                 capture_output=True, text=True, timeout=3, check=True).stdout
        else:
            out = subprocess.run([_qdbus(), os.environ["KONSOLE_DBUS_SERVICE"], os.environ["KONSOLE_DBUS_SESSION"],
                                  "org.kde.konsole.Session.foregroundProcessId"],
                                 capture_output=True, text=True, timeout=3, check=True).stdout
        return int(out.strip())
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None


def transport() -> str:
    """Pick the terminal to type into, innermost first, and only if it provably runs this session.

    Env vars leak into nested terminals (tmux started from Konsole inherits KONSOLE_DBUS_*), so a
    candidate is used only when its process is one of our ancestors. Otherwise: clipboard."""
    candidates = []
    if os.environ.get("TMUX_PANE") and shutil.which("tmux"):
        candidates.append("tmux")
    if os.environ.get("KONSOLE_DBUS_SERVICE") and os.environ.get("KONSOLE_DBUS_SESSION") and _qdbus():
        candidates.append("konsole")
    ours = _ancestors()
    for kind in candidates:
        if _target_pid(kind) in ours:
            return kind
    return "clipboard"


def send_text(kind: str, text: str) -> None:
    if kind == "konsole":
        subprocess.run([_qdbus(), os.environ["KONSOLE_DBUS_SERVICE"], os.environ["KONSOLE_DBUS_SESSION"],
                        "org.kde.konsole.Session.sendText", text], check=True, capture_output=True)
    elif kind == "tmux":
        subprocess.run(["tmux", "send-keys", "-t", os.environ["TMUX_PANE"], "-l", text], check=True)


def copy_to_clipboard(text: str) -> None:
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["pbcopy"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text.encode(), check=False)
            return


def dispatch(kind: str, prompt_file: str) -> None:
    """Runs detached after the hook has returned: wait for the block to land, /clear, re-send."""
    prompt = Path(prompt_file).read_text()
    Path(prompt_file).unlink(missing_ok=True)
    time.sleep(float(os.environ.get("NEW_TASK_SPLIT_DELAY", "1.0")))
    # Claude Code puts a blocked prompt back in the input box (seen on 2.1.310, undocumented), so
    # typing /clear straight away appends to it ("…text/clear") and submits a normal message.
    # Empty the box first: Ctrl+U clears the current line, Backspace joins the line above.
    send_text(kind, "\x15\x7f" * (prompt.count("\n") + 1))
    time.sleep(0.3)
    send_text(kind, "/clear")
    time.sleep(0.3)
    send_text(kind, "\r")
    time.sleep(float(os.environ.get("NEW_TASK_SPLIT_CLEAR_WAIT", "2.0")))
    # Multi-line text goes in as a bracketed paste so its newlines don't submit early.
    send_text(kind, f"\x1b[200~{prompt}\x1b[201~" if "\n" in prompt else prompt)
    time.sleep(0.3)
    send_text(kind, "\r")


def hand_off(prompt: str, session_id: str) -> str:
    """Start the move; return the transport used."""
    kind = transport()
    log({"session": session_id, "decision": "hand_off", "transport": kind})
    STATE.mkdir(parents=True, exist_ok=True)
    with open(STATE / "splits.jsonl", "a") as f:
        f.write(json.dumps({"t": time.time(), "hash": prompt_hash(prompt), "from": session_id}) + "\n")
    # Marker read by the SessionStart hook in the fresh session.
    (STATE / "pending-origin.json").write_text(json.dumps({"t": time.time(), "from": session_id}))
    if kind == "clipboard":
        copy_to_clipboard(prompt)
        return kind
    pf = STATE / f"pending-{session_id}.txt"
    pf.write_text(prompt)
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--dispatch", kind, str(pf)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return kind


# ---------- hook outputs ----------

def emit(obj: dict) -> None:
    print(json.dumps(obj))
    sys.exit(0)


def block(reason: str) -> None:
    emit({"decision": "block", "reason": reason,
          "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "suppressOriginalPrompt": True}})


def add_context(text: str) -> None:
    emit({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}})


# ---------- events ----------

def on_prompt(event: dict, cfg: dict) -> None:
    prompt = event.get("prompt", "")
    sid = event.get("session_id", "unknown")
    stripped = prompt.strip()
    low = stripped.lower()
    state = load_state(sid)

    if low in ("split off", "split on"):
        state["disabled"] = low == "split off"
        save_state(sid, state)
        block(f"new-task-split {'off' if state['disabled'] else 'on'} for this session.")
    if os.environ.get("NEW_TASK_SPLIT") == "off" or state.get("disabled"):
        sys.exit(0)
    if low.startswith(KEEP_PREFIXES):
        log({"session": sid, "decision": "kept_by_prefix"})
        sys.exit(0)
    # Slash commands, shell escapes, and machine-sent turns (task notifications, peer messages).
    if stripped[:1] in ("/", "!", "<") or not stripped:
        sys.exit(0)
    forced = low.startswith(FORCE_PREFIXES)
    if forced:
        # Re-send without the prefix, or the fresh session would split it again.
        prompt = stripped.split(":", 1)[1].lstrip()
    h = prompt_hash(prompt)
    if recently_split(h, sid):
        log({"session": sid, "decision": "returned_after_split", "hash": h})
        add_context("new-task-split had moved this exact message to a fresh session; the user "
                    "brought it back here, so it belongs to this conversation. Answer it here.")

    if not forced:
        if len(stripped) < MIN_PROMPT_CHARS:
            sys.exit(0)
        exchanges = read_exchanges(event.get("transcript_path", ""))
        if len(exchanges) < MIN_PRIOR_PROMPTS:
            sys.exit(0)
        t0 = time.time()
        try:
            p = score(prompt, exchanges, ntsconfig.MODEL_DIR)
        except Exception as e:  # fail open
            log({"session": sid, "decision": "error", "error": f"{type(e).__name__}: {e}"[:300]})
            sys.exit(0)
        threshold = float(os.environ.get("NEW_TASK_SPLIT_THRESHOLD", cfg.get("threshold") or 0.95))
        decision = "new_task" if p >= threshold else "continue"
        log({"session": sid, "hash": h, "preview": stripped[:120], "p_new_task": round(p, 4),
             "threshold": threshold, "decision": decision, "mode": cfg.get("mode", "split"),
             "model_revision": cfg.get("model_revision"), "ms": int((time.time() - t0) * 1000)})
        if decision != "new_task" or cfg.get("mode") == "shadow":
            sys.exit(0)
        why = f"p={p:.2f}"
    else:
        why = "forced with a new:/split: prefix"

    if split_just_now(sid):
        log({"session": sid, "decision": "skipped_loop_guard"})
        sys.exit(0)
    kind = hand_off(prompt, sid)
    undo = "Undo: /resume and pick the previous session, then re-send; it won't be split again."
    if kind == "clipboard":
        block(f"New task detected ({why}). Run /clear, then paste: the message is on your clipboard. {undo}")
    block(f"↪ New task detected ({why}). Moving it to a fresh session… {undo} "
          f"Start a message with 'same:' to keep it here, or type 'split off'.")


def on_session_start(event: dict) -> None:
    if event.get("source") != "clear":
        sys.exit(0)
    marker = STATE / "pending-origin.json"
    try:
        origin = json.loads(marker.read_text())
    except (OSError, ValueError):
        sys.exit(0)
    if time.time() - origin["t"] > 60:
        sys.exit(0)
    marker.unlink(missing_ok=True)
    emit({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": (
            "This session was started automatically by the new-task-split hook: the user's next "
            "message looked unrelated to their previous session "
            f"({origin['from']}), so it was moved here. If the user says the split was wrong, "
            "tell them to run /resume, choose that session, and re-send the message; the hook "
            "recognises a returned message and will not split it again."),
    }})


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--dispatch":
        try:
            dispatch(sys.argv[2], sys.argv[3])
            log({"decision": "dispatched", "transport": sys.argv[2]})
        except Exception as e:  # stdout/stderr are /dev/null here, so this log is the only trace
            log({"decision": "dispatch_error", "transport": sys.argv[2], "error": f"{type(e).__name__}: {e}"[:300]})
        return
    cfg = ntsconfig.load()
    # NEW_TASK_SPLIT=split|shadow enables the hook for this process only (the claudehook launcher),
    # whatever the config says; NEW_TASK_SPLIT=off is handled per prompt in on_prompt.
    forced = os.environ.get("NEW_TASK_SPLIT")
    if forced in ("split", "shadow"):
        cfg = {**cfg, "enabled": True, "mode": forced}
    if not cfg.get("enabled"):
        return
    event = json.load(sys.stdin)
    name = event.get("hook_event_name")
    if name == "UserPromptSubmit":
        on_prompt(event, cfg)
    elif name == "SessionStart":
        on_session_start(event)


if __name__ == "__main__":
    main()
