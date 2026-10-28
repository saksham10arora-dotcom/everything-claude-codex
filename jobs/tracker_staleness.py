#!/usr/bin/env python3
"""
Tracker Staleness Alert
Runs nightly. Checks key tracker files for last-modified date.
If any tracker > STALE_DAYS without update, drops an alert in inbox/.
"""

import os
import time
from datetime import datetime

ECX_VAULT = os.path.expanduser(os.environ.get("ECX_VAULT", "~/vault"))   # your notes folder
ECX_DATA = os.path.expanduser(os.environ.get("ECX_DATA", "~/.ecx/index"))  # where indexes live

VAULT = ECX_VAULT
INBOX = f"{VAULT}/inbox"
STALE_DAYS = 7

STALE_DAYS = int(os.environ.get("ECX_STALE_DAYS", STALE_DAYS))
# Every note named *tracker*.md counts as a tracker (e.g. personal/networking_tracker.md).
TRACKERS = sorted(
    (os.path.relpath(os.path.join(d, f), VAULT), f[:-3].replace("_tracker", "").replace("_", " ").title())
    for d, dirs, files in os.walk(VAULT)
    if not any(part.startswith(".") or part == "archive" for part in os.path.relpath(d, VAULT).split(os.sep))
    for f in files if f.endswith(".md") and "tracker" in f and "staleness" not in f
)

def check_staleness():
    now = time.time()
    stale = []
    for rel_path, label in TRACKERS:
        path = os.path.join(VAULT, rel_path)
        if not os.path.exists(path):
            continue
        age_days = (now - os.path.getmtime(path)) / 86400
        if age_days > STALE_DAYS:
            stale.append((label, rel_path, int(age_days)))

    if not stale:
        print("All trackers fresh.")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    # one rolling file, overwritten each run (daily files used to pile up in inbox/)
    alert_path = f"{VAULT}/personal/tracker-staleness.md"
    stale.sort(key=lambda x: -x[2])  # sort by days stale, worst first

    lines = [
        "---",
        "tags: [alert, staleness, inbox]",
        f"date: {today}",
        "---",
        "",
        f"# Tracker Staleness Alert: {today}",
        "",
        f"These trackers haven't been updated in {STALE_DAYS}+ days:",
        "",
    ]
    for label, path, days in stale:
        lines.append(f"- [ ] **{label}** (`{path}`): {days}d stale")

    lines += [
        "",
        "---",
        "Update or these lose their value as planning tools.",
    ]

    with open(alert_path, "w") as f:
        f.write("\n".join(lines))

    print(f"Staleness alert written: {alert_path} ({len(stale)} trackers)")

if __name__ == "__main__":
    check_staleness()
