#!/bin/bash
# SessionStart: capture first, organize later. Lists unsorted notes in inbox/
# so the agent files them (phone captures land here too).
V="${ECX_VAULT:-$HOME/vault}"
files=$(ls "$V"/inbox/*.md 2>/dev/null | sed 's|.*/||')
[ -n "$files" ] || exit 0
python3 - "$V" "$files" <<'PY'
import json, sys
vault, files = sys.argv[1], sys.argv[2]
msg = ("Unsorted notes are waiting in inbox/. Read each one and move it to the folder it belongs in "
       "(for example projects/, personal/, research/, studies/), keeping the filename.\n"
       f"Vault: {vault}\nFiles:\n{files}")
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": msg}}))
PY
