#!/usr/bin/env python3
"""PermissionRequest: never get asked to approve a read-only action.

Read, Glob, Grep, LS and web search can't change anything, so they are
approved automatically. Everything else falls through to the normal prompt.
"""
import json
import sys

READ_ONLY = {"Read", "Glob", "Grep", "LS", "WebSearch", "WebFetch", "NotebookRead"}

try:
    hook = json.load(sys.stdin)
    if hook.get("tool_name") in READ_ONLY:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "allow"}}}))
except Exception:
    pass
sys.exit(0)
