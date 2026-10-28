#!/usr/bin/env python3
"""MCP health check (idea from affaan-m/ECC, rewritten small).

    mcp_health.py pre    PreToolUse  ^mcp__  : block calls to a server whose
                                               dependency is down or that keeps failing
    mcp_health.py fail   PostToolUseFailure ^mcp__ : record the failure
    mcp_health.py ok     PostToolUse ^mcp__  : clear the failure record

Some servers "succeed" while broken (vault-graph answers "[no-context]" when
Ollama is down), so failures alone miss them: DEPS probes what each needs.
Never crashes the tool call: any error exits 0 silently.
"""
import json
import os
import socket
import sys
import time

STATE = os.path.expanduser("~/.claude/metrics/mcp-health.json")
WINDOW, MAX_FAILS = 600, 2          # block after 2 failures within 10 minutes

# server -> (host, port, what it is, how to fix)
DEPS = {
    "vault-graph": ("127.0.0.1", 11434, "Ollama", "start Ollama (`ollama serve` or open the Ollama app)"),
    "vault-router": None,           # falls back to vector search, so never block it
    "obsidian": ("127.0.0.1", 22360, "the Obsidian app's MCP plugin", "open Obsidian, then reconnect it in /mcp"),
    "screenpipe": ("127.0.0.1", 3030, "screenpipe", "start screenpipe (`sp on`)"),
}


def server_of(tool):
    parts = tool.split("__")
    return parts[1] if len(parts) > 2 else ""


def up(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(state, open(STATE, "w"))


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))


def main():
    mode = sys.argv[1]
    hook = json.load(sys.stdin)
    server = server_of(hook.get("tool_name", ""))
    if not server:
        return
    state = load()
    now = time.time()

    if mode == "pre":
        dep = DEPS.get(server)
        if dep and not up(dep[0], dep[1]):
            return deny(f"MCP server '{server}' needs {dep[2]} on port {dep[1]}, which is not running, "
                        f"so this call would fail or return empty results. Fix: {dep[3]}. "
                        f"Tell the user, and use another source meanwhile.")
        rec = state.get(server)
        if rec and now - rec["last"] < WINDOW and rec["count"] >= MAX_FAILS:
            return deny(f"MCP server '{server}' failed {rec['count']} times in the last "
                        f"{int((now - rec['first']) / 60) + 1} min (last error: {rec['error'][:200]}). "
                        f"Skipping it for now; ask the user to reconnect it via /mcp.")
    elif mode == "fail":
        rec = state.get(server)
        if not rec or now - rec["last"] > WINDOW:
            rec = {"count": 0, "first": now}
        rec.update(count=rec["count"] + 1, last=now, error=str(hook.get("error", ""))[:500])
        state[server] = rec
        save(state)
    elif mode == "ok" and server in state:
        del state[server]
        save(state)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
