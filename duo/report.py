"""The run report: the agents' own summary, then an action log duo builds from the raw events."""
import os
import re
import subprocess
import time

from duo.policy import OUTWARD, unwrap


def _t(ts):
    return time.strftime("%H:%M:%S", time.localtime(ts))


def _cell(s):
    return " ".join(str(s).split()).replace("|", "\\|")[:300]


def _outside(path, workdir):
    root = os.path.realpath(workdir)
    p = os.path.realpath(path)
    return not (p == root or p.startswith(root + os.sep))


def audit(events, workdir):
    opened = {e["id"]: e for e in events if e["kind"] == "card_open"}
    flags, rows, approvals = [], [], []
    for e in events:
        k, who = e["kind"], e["agent"]
        if k == "tool":
            detail = unwrap(e.get("detail", ""))
            rows.append((e["ts"], who, e.get("name", "tool"), detail, e.get("status", "")))
            if any(re.search(rx, detail, re.I) for rx, _ in OUTWARD):
                flags.append(f"{_t(e['ts'])} {who} ran an outward command: `{_cell(detail)}`")
            if str(e.get("name", "")).startswith("mcp__"):
                flags.append(f"{_t(e['ts'])} {who} used the tool `{e['name']}` {_cell(e.get('detail', ''))}")
        elif k == "file_change":
            paths = e.get("paths") or []
            rows.append((e["ts"], who, "file change", ", ".join(f"{kd} {p}" for p, kd in zip(paths, e.get("kinds") or [])),
                         e.get("status", "")))
            for p in paths:
                if _outside(p, workdir):
                    flags.append(f"{_t(e['ts'])} {who} changed a file outside the work folder: `{p}`")
        elif k == "blocked":
            rows.append((e["ts"], e.get("by", who), "blocked", e.get("summary") or e.get("detail", ""), "blocked"))
            flags.append(f"{_t(e['ts'])} blocked for {e.get('by', who)}: `{_cell(e.get('summary') or e.get('detail', ''))}` "
                         f"({e.get('reason', '')})")
        elif k == "card_resolved":
            c = opened.get(e["id"], {})
            approvals.append((e["ts"], c.get("by", ""), c.get("card", ""), c.get("summary", ""), e["decision"], e.get("note", "")))
            rows.append((e["ts"], c.get("by", ""), f"{c.get('card', '')} card", c.get("summary", ""), e["decision"]))
            if e["decision"] != "approve":
                flags.append(f"{_t(e['ts'])} you denied {c.get('by', '')}: `{_cell(c.get('summary', ''))}`"
                             f"{' (' + e['note'] + ')' if e.get('note') else ''}")
        elif k == "error":
            flags.append(f"{_t(e['ts'])} error: {_cell(e.get('text', ''))}")
    out = ["## Look at these first", ""]
    out += [f"- {f}" for f in flags] or ["None."]
    out += ["", "## Every action", "", "| time | agent | what | detail | result |", "|---|---|---|---|---|"]
    out += [f"| {_t(ts)} | {_cell(w)} | {_cell(n)} | {_cell(d)} | {_cell(r)} |" for ts, w, n, d, r in rows]
    out += ["", "## Approvals", ""]
    if approvals:
        out += ["| time | asked by | card | what | answer | note |", "|---|---|---|---|---|---|"]
        out += [f"| {_t(ts)} | {_cell(b)} | {_cell(c)} | {_cell(s)} | {_cell(d)} | {_cell(n)} |"
                for ts, b, c, s, d, n in approvals]
    else:
        out.append("No approval cards.")
    return "\n".join(out)


def _git(workdir, *args):
    try:
        return subprocess.run(["git", "-C", workdir, *args], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def write(run_dir, events, workdir, status):
    first = next((e for e in events if e["kind"] == "status" and e.get("goal")), {})
    meta = next((e for e in events if e["kind"] == "status" and e.get("base")), {})
    start = events[0]["ts"] if events else time.time()
    mins = int((time.time() - start) / 60)
    commits = _git(workdir, "log", "--oneline", f"{meta['base']}..HEAD") if meta.get("base") else ""
    summary_path = os.path.join(run_dir, "summary.md")
    summary = open(summary_path).read().strip() if os.path.exists(summary_path) else "No summary was written."
    parts = [f"# duo report", "",
             f"- Goal: {first.get('goal', '(unknown)')}",
             f"- Status: {status}",
             f"- Duration: {mins} min",
             f"- Branch: {meta.get('branch') or _git(workdir, 'rev-parse', '--abbrev-ref', 'HEAD') or '(none)'}",
             f"- Raw events: {os.path.join(run_dir, 'events.jsonl')}", "",
             "## Commits", "", f"```\n{commits}\n```" if commits else "No commits.", "",
             "# Their summary (written by the agents)", "", summary, "",
             "# Action log (written by duo from the raw events; the agents cannot edit it)", "",
             audit(events, workdir), ""]
    path = os.path.join(run_dir, "report.md")
    with open(path, "w") as f:
        f.write("\n".join(parts))
    return path
