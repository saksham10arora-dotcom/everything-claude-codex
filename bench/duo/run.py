#!/usr/bin/env python3
"""Benchmark: Claude alone vs Codex alone vs ecx duo on small tasks graded by hidden tests.

    python3 bench/duo/run.py [--tasks prices durations lru] [--configs claude codex duo] [--out results.json]

Each run gets a fresh throwaway git repo with the task's code and its weak visible tests. The hidden tests in
tasks/<name>/hidden/ are copied in only after the run, then scored. Same goal text for every contestant.
Solo runs: Claude Code with edits auto-accepted and only test/python commands allowed; Codex exec in a temporary
(ephemeral) session in duo's own Codex home, so nothing lands in your normal history. duo runs with cards
auto-approved (blocked actions stay blocked) and without your personal context.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ECX = os.path.dirname(os.path.dirname(HERE))
GOAL = ("Make {file} behave exactly as its docstring describes, including every edge case the docstring mentions. "
        "Add tests for the behaviour you fix. Keep the public function and class names the same.")
FILES = {"prices": "prices.py", "durations": "durations.py", "lru": "lru.py",
         "cron": "cron.py", "semver": "semver.py", "dst": "dst.py"}
SUITES = {"easy": ("tasks", ["prices", "durations", "lru"]), "hard": ("tasks_hard", ["cron", "semver", "dst"])}
TASKS_DIR = "tasks"
TIMEOUT = 20 * 60


def fresh_repo(task):
    d = tempfile.mkdtemp(prefix=f"duo-bench-{task}-")
    src = os.path.join(HERE, TASKS_DIR, task)
    for name in os.listdir(src):
        if name != "hidden":
            shutil.copy(os.path.join(src, name), d)
    git = ["git", "-C", d, "-c", "user.name=bench", "-c", "user.email=bench@example.com"]
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "task"], check=True)
    return d


def run_claude(d, goal):
    cmd = ["claude", "-p", goal, "--model", "sonnet", "--output-format", "json", "--no-session-persistence",
           "--settings", json.dumps({"disableAllHooks": True}), "--permission-mode", "acceptEdits",
           "--permission-prompts", "none",
           "--allowedTools", "Read", "Edit", "Write", "Glob", "Grep", "Bash(python3:*)", "Bash(python:*)", "Bash(ls:*)",
           "Bash(cat:*)"]
    r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=TIMEOUT)
    try:
        j = json.loads(r.stdout)
        return {"claude_cost_usd": j.get("total_cost_usd"), "turns": j.get("num_turns")}
    except ValueError:
        return {"error": (r.stderr or r.stdout)[-300:]}


def run_codex(d, goal):
    sys.path.insert(0, ECX)
    from duo.codex_agent import codex_home
    env = {**os.environ, "CODEX_HOME": codex_home()}
    cmd = ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "-s", "workspace-write", "--json",
           "-c", "features.codex_hooks=false", "-c", "features.plugins=false", goal]
    r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=TIMEOUT, env=env, stdin=subprocess.DEVNULL)
    tokens = 0
    for line in r.stdout.splitlines():
        try:
            o = json.loads(line)
        except ValueError:
            continue
        u = o.get("usage") or (o.get("msg") or {}).get("usage") or {}
        if isinstance(u, dict):
            tokens = max(tokens, sum(v for v in u.values() if isinstance(v, int)))
    return {"codex_tokens": tokens or None}


def run_duo(d, goal):
    env = {**os.environ, "ECX_DUO_AUTOAPPROVE": "1", "ECX_DUO_CATCHUP": "0", "ECX_DUO_CONTEXT": "", "ECX_VAULT": "",
           "ECX_USER": "the user"}
    r = subprocess.run([sys.executable, os.path.join(ECX, "duo", "duo.py"), goal, "--no-open", "--hours", "0.33"],
                       cwd=d, capture_output=True, text=True, timeout=TIMEOUT + 120, env=env, stdin=subprocess.DEVNULL)
    runs = sorted(os.listdir(os.path.join(d, ".duo"))) if os.path.isdir(os.path.join(d, ".duo")) else []
    out = {"status": (re.search(r"duo (\w+)\.", r.stdout) or [None, "?"])[1]}
    if runs:
        events = [json.loads(l) for l in open(os.path.join(d, ".duo", runs[-1], "events.jsonl"))]
        out["messages"] = sum(1 for e in events if e["kind"] == "message")
        out["cards"] = sum(1 for e in events if e["kind"] == "card_open")
        out["objections"] = sum(1 for e in events if e["kind"] == "signal" and e.get("objection"))
        out["verified"] = sum(1 for e in events if e["kind"] == "signal" and e.get("verified"))
        for who in ("claude", "codex"):
            u = [e for e in events if e["kind"] == "usage" and e["agent"] == who]
            if len(u) >= 2:
                out[f"{who}_5h_pct_used"] = (u[-1].get("five_hour") or 0) - (u[0].get("five_hour") or 0)
    return out


def score(d, task):
    shutil.copy(os.path.join(HERE, TASKS_DIR, task, "hidden", "test_hidden.py"), os.path.join(d, "test_hidden_bench.py"))
    try:
        r = subprocess.run([sys.executable, "-m", "unittest", "-v", "test_hidden_bench"], cwd=d, capture_output=True,
                           text=True, timeout=180)
    except subprocess.TimeoutExpired:
        return 0, -1  # the code hangs on the hidden tests: counts as 0
    passed = len(re.findall(r" \.\.\. ok$", r.stderr, re.M))
    total = int((re.search(r"Ran (\d+) test", r.stderr) or [0, 0])[1])
    return passed, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=list(SUITES), default="easy")
    ap.add_argument("--tasks", nargs="+")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--configs", nargs="+", default=["claude", "codex", "duo"])
    ap.add_argument("--out", default=os.path.join(HERE, "results.json"))
    a = ap.parse_args()
    global TASKS_DIR
    TASKS_DIR, default_tasks = SUITES[a.suite]
    a.tasks = a.tasks or default_tasks
    results = json.load(open(a.out)) if os.path.exists(a.out) else []
    for rep in range(a.repeat):
      for task in a.tasks:
        for cfg in a.configs:
            d = fresh_repo(task)
            goal = GOAL.format(file=FILES[task])
            t0 = time.time()
            try:
                extra = {"claude": run_claude, "codex": run_codex, "duo": run_duo}[cfg](d, goal)
            except subprocess.TimeoutExpired:
                extra = {"error": "timeout"}
            minutes = round((time.time() - t0) / 60, 1)
            passed, total = score(d, task)
            row = {"suite": a.suite, "rep": rep + 1, "task": task, "config": cfg, "hidden_passed": passed, "hidden_total": total, "minutes": minutes,
                   "workdir": d, **extra}
            results.append(row)
            json.dump(results, open(a.out, "w"), indent=1)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
