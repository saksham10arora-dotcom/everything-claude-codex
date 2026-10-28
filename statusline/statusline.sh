#!/bin/bash
# Status line: context bar + unread mail from Codex.
#   ctx [████░░░░░░] 42%  ·  ✉ 2 from Codex
read -r DATA
PERCENT=$(echo "$DATA" | python3 -c 'import json,sys; print(int(float(json.load(sys.stdin).get("context_window",{}).get("used_percentage") or 0)))' 2>/dev/null)
[ -n "$PERCENT" ] || exit 0
BAR=$(python3 -c "p=$PERCENT//10; print('█'*p + '░'*(10-p))")
if [ "$PERCENT" -ge 75 ]; then C="\033[31m"; elif [ "$PERCENT" -ge 50 ]; then C="\033[33m"; else C="\033[32m"; fi
R="\033[0m"
printf "${C}ctx [%s] %d%%${R}" "$BAR" "$PERCENT"
UNREAD=$(python3 - <<'PY' 2>/dev/null
import json, os
d = os.path.expanduser("~/.agent-sync")
try:
    last = json.load(open(os.path.join(d, "mail-read-claude.json"))).get("last", 0)
except Exception:
    last = 0
try:
    print(sum(1 for l in open(os.path.join(d, "mail.jsonl")) if l.strip() and (m := json.loads(l))["to"] == "claude" and m["id"] > last))
except Exception:
    print(0)
PY
)
[ "${UNREAD:-0}" -gt 0 ] && printf "  ·  \033[36m✉ %s from Codex\033[0m" "$UNREAD"
exit 0
