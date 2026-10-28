#!/usr/bin/env python3
"""Stop hook: macOS notification when a reply that took a while is done
(idea from affaan-m/ECC, rewritten small). Quick replies stay silent.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

MIN_SECONDS = 45
TAIL = 2_000_000


def tail_entries(path):
    with open(path, "rb") as f:
        f.seek(max(0, os.path.getsize(path) - TAIL))
        lines = f.read().splitlines()[1:]
    out = []
    for raw in lines:
        try:
            out.append(json.loads(raw))
        except Exception:
            pass
    return out


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def main():
    hook = json.load(sys.stdin)
    entries = tail_entries(hook["transcript_path"])
    started, reply = None, ""
    for e in entries:
        if e.get("isSidechain") or e.get("isMeta"):
            continue
        content = (e.get("message") or {}).get("content")
        if e.get("type") == "user" and isinstance(content, str) and not content.lstrip().startswith("<"):
            started, reply = e.get("timestamp"), ""
        elif e.get("type") == "assistant":
            reply = text_of(content) or reply
    if not started:
        return
    t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
    secs = (datetime.now(timezone.utc) - t0).total_seconds()
    if secs < MIN_SECONDS:
        return
    project = os.path.basename((hook.get("cwd") or "").rstrip("/")) or "Claude"
    body = " ".join(reply.split())[:140] or "Done"
    mins = f"{int(secs // 60)}m {int(secs % 60)}s" if secs >= 60 else f"{int(secs)}s"
    script = f"display notification {json.dumps(body)} with title {json.dumps('Claude done · ' + project)} subtitle {json.dumps('took ' + mins)}"
    subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
