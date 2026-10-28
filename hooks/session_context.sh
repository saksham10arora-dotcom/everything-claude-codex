#!/bin/bash
# SessionStart: load who you are and what's going on before the first message.
# Injects .remember/hot.md (current state), recent.md (last sessions) and the
# top of archive.md (older weeks) from your vault.
R="${ECX_VAULT:-$HOME/vault}/.remember"
ctx=""
[ -f "$R/hot.md" ]     && ctx="=== HOT CONTEXT (current state) ===
$(cat "$R/hot.md")

"
[ -f "$R/recent.md" ]  && ctx="${ctx}=== RECENT SESSIONS ===
$(cat "$R/recent.md")

"
[ -f "$R/archive.md" ] && ctx="${ctx}=== ARCHIVE (older weeks) ===
$(head -60 "$R/archive.md")
"
[ -n "$ctx" ] || exit 0
python3 -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":sys.stdin.read()[:10000]}}))' <<<"$ctx"
