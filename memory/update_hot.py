#!/usr/bin/env python3
"""
PostCompact hook: reads compaction summary from stdin, updates hot.md automatically.
Fired by Claude Code after every /compact.
"""
import os
import json, sys, re
from datetime import datetime
from pathlib import Path

ECX_VAULT = os.path.expanduser(os.environ.get("ECX_VAULT", "~/vault"))   # your notes folder
ECX_DATA = os.path.expanduser(os.environ.get("ECX_DATA", "~/.ecx/index"))  # where indexes live

HOT = Path(ECX_VAULT) / ".remember" / "hot.md"
TMP = Path(ECX_VAULT) / ".remember" / "tmp" / "last-compaction.md"
TMP.parent.mkdir(parents=True, exist_ok=True)

try:
    raw = sys.stdin.read().strip()
    d = json.loads(raw) if raw else {}
except Exception:
    d = {}

summary = d.get("summary", "").strip()
ts = datetime.now().strftime("%Y-%m-%d %H:%M")

# Always save to last-compaction.md
TMP.write_text(f"# Compaction {ts}\n\n{summary}\n")

if not summary:
    sys.exit(0)

# Truncate summary to keep hot.md lean
snippet = summary[:2500] + ("..." if len(summary) > 2500 else "")

# Build replacement block
block = f"\n## LAST SESSION (auto-updated)\n_{ts}_\n\n{snippet}\n\n---\n\n"

if not HOT.exists():
    sys.exit(0)
content = HOT.read_text()

# Update timestamp line
content = re.sub(r"# Updated: .*", f"# Updated: {ts} (auto)", content)

# Replace existing block or insert before ## WHO
if "## LAST SESSION (auto-updated)" in content:
    content = re.sub(
        r"\n## LAST SESSION \(auto-updated\).*?---\n\n",
        block,
        content,
        flags=re.DOTALL,
    )
else:
    content = content.replace("\n## WHO", block + "## WHO", 1)

HOT.write_text(content)
print(f"hot.md updated at {ts}")
