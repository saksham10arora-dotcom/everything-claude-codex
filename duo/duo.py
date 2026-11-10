#!/usr/bin/env python3
"""ecx duo: Claude and Codex work on one goal together while you watch, talk, approve and stop.

    ecx duo "make the failing login test pass" [--best] [--hours 2] [--user Saksham]
"""
import argparse
import asyncio
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from duo import report  # noqa: E402
from duo.claude_agent import ClaudeAgent  # noqa: E402
from duo.codex_agent import CodexAgent  # noqa: E402
from duo.events import EventLog  # noqa: E402
from duo.orchestrator import Limits, Orchestrator  # noqa: E402
from duo.policy import Ctx  # noqa: E402
from duo.server import start_server  # noqa: E402

NOT_GIT = "This folder is not a git repo."


def git(workdir, *args, check=False):
    r = subprocess.run(["git", "-C", workdir, *args], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r


def slug(goal):
    words = re.findall(r"[a-z0-9]+", goal.lower())[:5]
    return "-".join(words)[:40].strip("-") or "run"


def preflight(workdir):
    problems = []
    if git(workdir, "rev-parse", "--is-inside-work-tree").returncode:
        problems.append(NOT_GIT)
    else:
        dirty = [l for l in git(workdir, "status", "--porcelain", "--untracked-files=no").stdout.splitlines() if not l[3:].startswith(".duo/")]
        if dirty:
            problems.append("Commit or stash your changes first, so their commits never mix with your work.")
        if not git(workdir, "rev-parse", "--verify", "HEAD").stdout.strip():
            problems.append("This repo has no commits yet. Make a first commit, then start duo.")
    vault = os.environ.get("ECX_VAULT", "")
    if vault:
        v, w = os.path.realpath(os.path.expanduser(vault)), os.path.realpath(workdir)
        if w == v or w.startswith(v + os.sep):
            problems.append("This is your vault. duo does not run in the vault yet (it commits straight to master).")
    for exe in ("claude", "codex"):
        if not shutil.which(exe):
            problems.append(f"`{exe}` is not on your PATH.")
    return problems


def allow_rule_warnings(workdir):
    out = []
    for name in ("settings.json", "settings.local.json"):
        p = os.path.join(workdir, ".claude", name)
        try:
            allow = (json.load(open(p)).get("permissions") or {}).get("allow") or []
        except (OSError, ValueError):
            continue
        if allow:
            out.append(f"{p} pre-allows {', '.join(allow[:6])}{' ...' if len(allow) > 6 else ''}. Claude will do those "
                       "without asking duo, so they get no approval card.")
    return out


def add_exclude(workdir):
    path = git(workdir, "rev-parse", "--git-path", "info/exclude").stdout.strip()
    path = path if os.path.isabs(path) else os.path.join(workdir, path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = open(path).read().splitlines() if os.path.exists(path) else []
    if ".duo/" not in lines:
        with open(path, "a") as f:
            f.write(("\n" if lines and lines[-1] else "") + ".duo/\n")


def snapshot(workdir):
    files = git(workdir, "ls-files", "-z").stdout.split("\0") + \
        git(workdir, "ls-files", "--others", "--exclude-standard", "-z").stdout.split("\0")
    return {os.path.join(workdir, f) for f in files if f}


PROTECTED_FILE = "~/.config/ecx/protected"


def protected_paths():
    """ECX_PROTECTED (colon-separated) plus one path per line in ~/.config/ecx/protected."""
    paths = [p for p in os.environ.get("ECX_PROTECTED", "").split(":") if p]
    f = os.path.expanduser(PROTECTED_FILE)
    if os.path.isfile(f):
        paths += [ln.strip() for ln in open(f) if ln.strip() and not ln.strip().startswith("#")]
    out = []
    for p in paths:
        p = os.path.expanduser(p)
        if p not in out:
            out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ecx duo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("goal")
    ap.add_argument("--best", action="store_true", help="top models and high effort (uses more of your quota)")
    ap.add_argument("--hours", type=float, default=2.0, help="pause and ping after this long (default 2)")
    ap.add_argument("--claude-model")
    ap.add_argument("--codex-model")
    ap.add_argument("--user", default=os.environ.get("ECX_USER") or os.environ.get("AGENT_SYNC_USER") or "the user")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)

    workdir = os.path.realpath(os.getcwd())
    problems = preflight(workdir)
    if NOT_GIT in problems and sys.stdin.isatty():
        if input("Not a git repo. Run git init here and commit the current files as a starting point? [y/N] ").lower() == "y":
            git(workdir, "init", "-q", check=True)
            git(workdir, "add", "-A", check=True)
            git(workdir, "commit", "-qm", "Starting point before duo", check=True)
            problems = preflight(workdir)
    if problems:
        print("duo can't start:\n" + "\n".join(f"  - {p}" for p in problems), file=sys.stderr)
        return 1
    for w in allow_rule_warnings(workdir):
        print(f"warning: {w}", file=sys.stderr)
    if not protected_paths():
        print(f"warning: no protected paths set. Put folders agents must never touch in {PROTECTED_FILE} "
              "(one per line) or ECX_PROTECTED.", file=sys.stderr)

    ts = time.strftime("%Y%m%d-%H%M%S")
    previous = git(workdir, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    base = git(workdir, "rev-parse", "HEAD").stdout.strip()
    branch = f"duo/{ts}-{slug(a.goal)}"
    git(workdir, "checkout", "-q", "-b", branch, check=True)
    run_dir = os.path.join(workdir, ".duo", ts)
    os.makedirs(run_dir)
    add_exclude(workdir)

    log = EventLog(os.path.join(run_dir, "events.jsonl"))
    log.add("duo", "status", status="starting", base=base, branch=branch, previous=previous)
    readable = [os.environ["ECX_VAULT"]] if os.environ.get("ECX_VAULT") else []
    ctx = Ctx(workdir=workdir, phase="plan", existed=snapshot(workdir), protected=protected_paths(), readable=readable)
    effort = "high" if a.best else "medium"
    agents = {"claude": ClaudeAgent(workdir, a.claude_model or ("opus" if a.best else "sonnet"), effort),
              "codex": CodexAgent(workdir, a.codex_model, effort)}
    for n, agent in agents.items():
        agent.stderr_path = os.path.join(run_dir, f"{n}.stderr.log")
    orch = Orchestrator(workdir, run_dir, agents, log, ctx, a.user, Limits(hours=a.hours), report_fn=report.write)

    async def go():
        loop = asyncio.get_running_loop()
        orch.loop = loop
        url, stop = start_server(log, orch, run_dir, a.port)
        loop.add_signal_handler(signal.SIGINT, lambda: orch.control("stop"))
        print(f"duo is running on branch {branch}\nWatch and talk: {url}\nCtrl-C stops both agents.", flush=True)
        if not a.no_open:
            webbrowser.open(url)
        try:
            return await orch.run(a.goal)
        finally:
            stop()

    status = asyncio.run(go())
    print(f"\nduo {status}. Report: {os.path.join(run_dir, 'report.md')}\nBranch {branch}; "
          f"go back with: git checkout {previous}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
