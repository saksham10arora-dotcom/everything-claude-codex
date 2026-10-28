#!/usr/bin/env python3
"""Token usage report from ~/.claude/metrics/usage.jsonl.

    usage_report.py            last 7 days, by day and by project
    usage_report.py 30         last 30 days
"""
import json
import os
import sys
import time
from collections import defaultdict

LOG = os.path.expanduser("~/.claude/metrics/usage.jsonl")
days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
since = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))

latest = {}                                   # rows are cumulative: keep the last per session
for line in open(LOG):
    r = json.loads(line)
    latest[r["session"]] = r


def fmt(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


by_day, by_proj, by_model = defaultdict(lambda: [0, 0, 0]), defaultdict(lambda: [0, 0, 0]), defaultdict(lambda: [0, 0, 0])
for r in latest.values():
    day = r["ts"][:10]
    if day < since:
        continue
    for model, m in r["models"].items():
        if model == "<synthetic>":
            continue
        fresh = m["input_tokens"] + m["cache_creation_input_tokens"]
        for bucket in (by_day[day], by_proj[r["project"]], by_model[model]):
            bucket[0] += fresh
            bucket[1] += m["cache_read_input_tokens"]
            bucket[2] += m["output_tokens"]

for title, data in (("Day", by_day), ("Project", by_proj), ("Model", by_model)):
    print(f"\n{title:<28} {'new in':>8} {'cached':>8} {'out':>8}")
    for k, (a, b, c) in sorted(data.items(), key=lambda kv: kv[0] if title == "Day" else -sum(kv[1])):
        print(f"{k[:28]:<28} {fmt(a):>8} {fmt(b):>8} {fmt(c):>8}")
