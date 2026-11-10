#!/usr/bin/env python3
"""SWE-bench Verified: Claude alone vs Codex alone vs ecx duo on real GitHub issues, graded by the official harness.

    python3 bench/duo/swe.py --instances django__django-13128 ... --out swe_runs/   (produces predictions per config)
    then: python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Verified \\
          --predictions_path swe_runs/preds_<config>.jsonl --run_id <config> --namespace none

Each run gets a fresh checkout of the project at the issue's base commit and the issue text as its goal. The
agent's diff (minus test files and duo's run folder) is the prediction. Same models as the small benchmark:
Claude Code on Sonnet, Codex on its default model, duo on both.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run as small  # noqa: E402  (run_claude, run_codex, run_duo)

PROMPT = """You are working in a checkout of {repo}. Resolve this GitHub issue by changing the library's source code.

<issue>
{issue}
</issue>

Make the smallest correct change that fixes the issue for all the cases it describes. Do not modify or delete existing
tests. You may not be able to run the project's test suite here; reason carefully about the code instead."""


def checkout(cache, repo, base, dest):
    src = os.path.join(cache, repo.replace("/", "__"))
    if not os.path.isdir(src):
        subprocess.run(["git", "clone", "-q", f"https://github.com/{repo}.git", src], check=True)
    subprocess.run(["git", "-C", src, "worktree", "add", "-q", "--detach", dest, base], check=True)
    return dest


def diff(d, base):
    out = subprocess.run(["git", "-C", d, "add", "-A"], capture_output=True)
    names = subprocess.run(["git", "-C", d, "diff", "--cached", "--name-only", base], capture_output=True, text=True).stdout.split()
    keep = [n for n in names if not n.startswith(".duo/") and "/tests/" not in f"/{n}" and not os.path.basename(n).startswith("test_")
            and not n.endswith("_test.py")]
    if not keep:
        return ""
    return subprocess.run(["git", "-C", d, "diff", "--cached", base, "--", *keep], capture_output=True, text=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=os.path.join(HERE, "swe_hard.json"))
    ap.add_argument("--instances", nargs="+", required=True)
    ap.add_argument("--configs", nargs="+", default=["claude", "codex", "duo"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--cache", default=os.path.expanduser("~/.ecx-duo/swe-repos"))
    a = ap.parse_args()
    small.TIMEOUT, small.DUO_HOURS = 40 * 60, "0.66"  # real repos need longer than the small tasks
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.cache, exist_ok=True)
    data = {r["instance_id"]: r for r in json.load(open(a.dataset))}
    log = os.path.join(a.out, "runs.jsonl")
    for iid in a.instances:
        r = data[iid]
        goal = PROMPT.format(repo=r["repo"], issue=r["problem_statement"].strip())
        for cfg in a.configs:
            d = os.path.join(a.out, "work", f"{iid}__{cfg}")
            if os.path.exists(d):
                continue  # resume: this run already happened
            checkout(a.cache, r["repo"], r["base_commit"], d)
            subprocess.run(["git", "-C", d, "-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-q",
                            "--allow-empty", "-m", "base"], check=True)
            t0 = time.time()
            try:
                extra = {"claude": small.run_claude, "codex": small.run_codex, "duo": small.run_duo}[cfg](d, goal)
            except subprocess.TimeoutExpired:
                extra = {"error": "timeout"}
            patch = diff(d, r["base_commit"])
            row = {"instance_id": iid, "config": cfg, "minutes": round((time.time() - t0) / 60, 1),
                   "patch_lines": patch.count("\n"), **extra}
            with open(log, "a") as f:
                f.write(json.dumps(row) + "\n")
            with open(os.path.join(a.out, f"preds_{cfg}.jsonl"), "a") as f:
                f.write(json.dumps({"instance_id": iid, "model_name_or_path": cfg, "model_patch": patch}) + "\n")
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
