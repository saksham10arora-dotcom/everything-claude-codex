#!/usr/bin/env python3
"""Stop hook: token usage per chat (idea from affaan-m/ECC, rewritten small).

Reads only the new part of the transcript each time (byte cursor), sums the
usage of each assistant message once (a message is logged once per content
block with identical usage, so it is deduped by message id), and appends a
cumulative snapshot per session to ~/.claude/metrics/usage.jsonl.
Report: python3 ~/.claude/hooks/usage_report.py
"""
import json
import os
import sys
import time

DIR = os.path.expanduser("~/.claude/metrics")
LOG = os.path.join(DIR, "usage.jsonl")
KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def main():
    hook = json.load(sys.stdin)
    sid, path = hook["session_id"], hook["transcript_path"]
    cur_path = os.path.join(DIR, "cursors", sid + ".json")
    os.makedirs(os.path.dirname(cur_path), exist_ok=True)
    try:
        cur = json.load(open(cur_path))
    except Exception:
        cur = {"offset": 0, "last_id": None, "models": {}}
    size = os.path.getsize(path)
    if size < cur["offset"]:
        cur = {"offset": 0, "last_id": None, "models": {}}
    if size == cur["offset"]:
        return
    with open(path, "rb") as f:
        f.seek(cur["offset"])
        for raw in f:
            if not raw.endswith(b"\n"):
                break
            cur["offset"] += len(raw)
            try:
                e = json.loads(raw)
            except Exception:
                continue
            msg = e.get("message") or {}
            usage = msg.get("usage")
            if e.get("type") != "assistant" or not usage or msg.get("id") == cur["last_id"]:
                continue
            cur["last_id"] = msg.get("id")
            m = cur["models"].setdefault(msg.get("model", "?"), dict.fromkeys(KEYS, 0) | {"messages": 0})
            for k in KEYS:
                m[k] += usage.get(k) or 0
            m["messages"] += 1
    json.dump(cur, open(cur_path, "w"))
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "session": sid,
           "project": os.path.basename((hook.get("cwd") or "").rstrip("/")), "models": cur["models"]}
    with open(LOG, "a") as f:
        f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
