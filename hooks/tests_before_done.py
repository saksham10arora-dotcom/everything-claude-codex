#!/usr/bin/env python3
"""Tests before done: a Stop hook for Claude Code and Codex.

When the agent tries to finish, run the project's tests. If they fail, it
can't say "done": the hook sends it back to work with the failing output.
Both agents send the same Stop payload ({cwd, session_id, stop_hook_active})
and both read {"decision": "block", "reason": ...} as "keep going", so one
script covers both.

Runs only in a git repo, only when something changed since the last green run
(HEAD, tracked changes, untracked files), and only when it finds a test command:
    .ecx/test-command   one line in the repo ("off" turns the hook off there)
    $ECX_TEST_CMD
    package.json "test" script, pytest config, tests/ with test_*.py,
    Cargo.toml, go.mod, a Makefile with a "test:" target
If the test runner itself is missing (exit 127) it tells you instead of blocking.
After 3 failed tries in a row it lets the agent stop and tells you, instead of
looping. Turn it off everywhere with ECX_TEST_ON_STOP=0.
Never breaks a session: any error exits 0 silently.
"""
import hashlib
import json
import os
import re
import subprocess
import sys

STATE = os.path.expanduser("~/.ecx/state/tests-before-done.json")
MAX_TRIES = int(os.environ.get("ECX_TEST_MAX_TRIES", "3"))
TIMEOUT = int(os.environ.get("ECX_TEST_TIMEOUT", "300"))
TAIL = 40                                      # lines of test output handed back to the agent
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules",
              ".venv", "venv", "target", "dist", "build", ".next", "coverage"}


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, timeout=20).stdout


def toplevel(cwd):
    out = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=10)
    return out.stdout.strip() if out.returncode == 0 else None


def fingerprint(root):
    """Hash of what the agent could have changed. Returns (hash, anything_uncommitted)."""
    h = hashlib.sha256(git(root, "rev-parse", "HEAD") + git(root, "diff", "HEAD"))
    untracked = git(root, "ls-files", "--others", "--exclude-standard").decode(errors="replace").splitlines()
    untracked = [p for p in untracked if not CACHE_DIRS & set(p.split("/")[:-1])][:5000]
    for p in untracked:                        # name, size and mtime catch edits to new files
        try:
            st = os.stat(os.path.join(root, p))
            h.update(f"{p}:{st.st_size}:{st.st_mtime_ns}\n".encode())
        except OSError:
            pass
    dirty = bool(untracked) or bool(git(root, "status", "--porcelain", "--untracked-files=no").strip())
    return h.hexdigest(), dirty


def read(root, name):
    try:
        with open(os.path.join(root, name)) as f:
            return f.read()
    except OSError:
        return ""


def test_command(root):
    own = read(root, os.path.join(".ecx", "test-command")).strip()
    if own:
        return own
    if os.environ.get("ECX_TEST_CMD"):
        return os.environ["ECX_TEST_CMD"]
    has = lambda name: os.path.exists(os.path.join(root, name))
    if has("package.json"):
        try:
            script = json.loads(read(root, "package.json")).get("scripts", {}).get("test", "")
        except ValueError:
            script = ""
        if script and "no test specified" not in script:
            return "npm test --silent"
    if has("pytest.ini") or has("conftest.py") or "[tool.pytest" in read(root, "pyproject.toml"):
        return "python3 -m pytest -q"
    for d in ("tests", "test"):
        if os.path.isdir(os.path.join(root, d)) and any(
                n.startswith("test") and n.endswith(".py") for n in os.listdir(os.path.join(root, d))):
            return f"python3 -m unittest discover -s {d}"
    if has("Cargo.toml"):
        return "cargo test -q"
    if has("go.mod"):
        return "go test ./..."
    if re.search(r"^test:", read(root, "Makefile"), re.M):
        return "make test"
    return None


def load():
    try:
        with open(STATE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}
    state.setdefault("repos", {})
    state.setdefault("tries", {})
    return state


def save(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    state["tries"] = dict(list(state["tries"].items())[-50:])
    with open(STATE, "w") as f:
        json.dump(state, f)


def say(**out):
    print(json.dumps(out))


def main():
    if os.environ.get("ECX_TEST_ON_STOP") == "0":
        return
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    root = toplevel(payload.get("cwd") or os.getcwd())
    cmd = test_command(root) if root else None
    if not cmd or cmd == "off":
        return

    state = load()
    session = payload.get("session_id") or "?"
    if not payload.get("stop_hook_active"):    # a new turn, not a retry we caused: reset the count
        state["tries"].pop(session, None)
    fp, dirty = fingerprint(root)
    known = state["repos"].get(root)
    if fp == known or (known is None and not dirty):
        state["repos"][root] = fp               # nothing changed since the last green run (or first visit)
        save(state)
        return

    try:
        p = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True,
                           timeout=TIMEOUT, env={**os.environ, "CI": "1"})
    except subprocess.TimeoutExpired:
        save(state)
        say(systemMessage=f"ECX: tests timed out after {TIMEOUT}s (`{cmd}`), so they didn't block the stop.")
        return

    if p.returncode == 127:                     # the test runner isn't installed: nothing the agent broke
        save(state)
        say(systemMessage=f"ECX: couldn't run the tests (`{cmd}`: command not found). "
                          "Install the project's dependencies to turn the check on.")
        return

    if p.returncode == 0:
        state["repos"][root] = fingerprint(root)[0]   # after the run, so files the tests write don't count
        state["tries"].pop(session, None)
        save(state)
        return

    tries = state["tries"].get(session, 0) + 1
    if tries > MAX_TRIES:
        state["tries"].pop(session, None)
        save(state)
        say(systemMessage=f"ECX: tests still failing after {MAX_TRIES} tries (`{cmd}`). Stopped so you can take a look.")
        return
    state["tries"][session] = tries
    save(state)
    tail = "\n".join((p.stdout + p.stderr).strip().splitlines()[-TAIL:])[-4000:]
    say(decision="block",
        reason=f"Tests failed (`{cmd}`, exit {p.returncode}), so this isn't done yet. Fix what's failing below, "
               f"then finish again. Attempt {tries} of {MAX_TRIES}.\n\n{tail}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
