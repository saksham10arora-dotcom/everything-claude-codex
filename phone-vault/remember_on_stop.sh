#!/bin/bash
# Stop hook: ask the remember plugin to save a summary after each reply.
# The plugin only saves after tool calls, so fast chats with no tools (IPL
# auction, 2026-10-11) never got summarized. Its own cooldown (120 s) and
# min-3-human-messages threshold still apply, so this is cheap.
sid=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("session_id",""))' 2>/dev/null)
[ -n "$sid" ] || exit 0
P=$(ls -d "$HOME"/.claude/plugins/cache/claude-plugins-official/remember/*/ 2>/dev/null | sort -V | tail -1)
[ -n "$P" ] || exit 0
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-${ECX_VAULT:-$HOME/vault}}"
unset REMEMBER_TRANSCRIPT_PATH
(nohup bash "${P}scripts/save-session.sh" "$sid" >/dev/null 2>&1 &)
exit 0
