#!/usr/bin/env python3
"""PreToolUse (Bash): block catastrophic shell commands, ask before risky ones.

Reads the command from stdin JSON (tool_input.command). Many guards online read
an environment variable that Claude Code never sets, so they silently allow
everything; this one is tested against the real hook payload.
"""
import json
import re
import sys

BLOCK = [
    (r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+(-\S+\s+)*(/|~|\$HOME|/\*|~/\*)(\s|$)", "deletes your whole disk or home folder"),
    (r"\bmkfs(\.\w+)?\b", "formats a disk"),
    (r"\bdd\b.*\bof=/dev/(disk|sd|nvme)", "overwrites a raw disk"),
    (r":\(\)\s*\{\s*:\|:&\s*\};:", "is a fork bomb"),
    (r"\bchmod\s+(-R\s+)?777\s+(/|~|\$HOME)(\s|$)", "opens your whole system to everyone"),
]
ASK = [
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r", "deletes files recursively"),
    (r"\bsudo\b", "runs as root"),
    (r"\bgit\s+push\b.*(--force\b|-f\b)", "force-pushes and can overwrite history"),
    (r"\bgit\s+reset\s+--hard\b", "throws away uncommitted work"),
    (r"\bDROP\s+(TABLE|DATABASE)\b|\bTRUNCATE\s+TABLE\b", "deletes database data"),
    (r"\bchmod\s+(-R\s+)?777\b", "makes files writable by everyone"),
]


def decide(cmd):
    for rx, why in BLOCK:
        if re.search(rx, cmd, re.I):
            return "deny", f"Blocked: this command {why}. Ask the user to run it themselves if they really mean it."
    for rx, why in ASK:
        if re.search(rx, cmd, re.I):
            return "ask", f"This command {why}."
    return None, None


def main():
    hook = json.load(sys.stdin)
    if hook.get("tool_name") != "Bash":
        return
    decision, reason = decide((hook.get("tool_input") or {}).get("command", ""))
    if decision:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
