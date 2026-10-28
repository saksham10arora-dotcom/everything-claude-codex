#!/bin/bash
# Stop: move this session's running notes (.remember/now.md) into today's log,
# so nothing said in a session is lost when the window closes.
R="${ECX_VAULT:-$HOME/vault}/.remember"
now="$R/now.md"; today="$R/today-$(date '+%Y-%m-%d').md"
if [ -s "$now" ]; then cat "$now" >> "$today" && : > "$now"; fi
exit 0
