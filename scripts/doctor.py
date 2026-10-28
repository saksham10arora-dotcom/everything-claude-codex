#!/usr/bin/env python3
"""ECX doctor: check every moving part and say exactly how to fix what's broken.

    python3 scripts/doctor.py --vault ~/vault

Exists because silent failure is the real enemy: a nightly index job once
failed 120 nights in a row without anyone noticing. Run this, or let /daily do it.
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

ECX = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
DATA = os.path.expanduser(os.environ.get("ECX_DATA", "~/.ecx/index"))
results = []


def check(ok, name, fix=""):
    results.append(ok)
    print(f"  {'✓' if ok else '✗'} {name}" + ("" if ok or not fix else f"\n      fix: {fix}"))


def warn(name, note):
    print(f"  ! {name}\n      {note}")


def load(path):
    try:
        return json.load(open(path))
    except Exception:
        return {}


def commands(cfg):
    return [h.get("command", "") for groups in cfg.get("hooks", {}).values() for g in groups for h in g.get("hooks", [])]


def port_open(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def age_days(path):
    newest = 0
    for d, _, files in os.walk(path):
        for f in files:
            newest = max(newest, os.path.getmtime(os.path.join(d, f)))
    return (time.time() - newest) / 86400 if newest else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.environ.get("ECX_VAULT", os.path.join(HOME, "vault")))
    vault = os.path.realpath(os.path.expanduser(ap.parse_args().vault))
    print(f"\nECX doctor · vault: {vault}\n")

    print("Core")
    check(sys.version_info >= (3, 9), f"python {sys.version.split()[0]}", "install Python 3.9+")
    check(shutil.which("git") is not None, "git", "install git")
    check(os.path.isfile(os.path.join(vault, ".remember", "hot.md")), "hot.md (who you are, right now)", "run scripts/install.py")
    skills = os.listdir(os.path.join(ECX, "skills"))
    linked = [s for s in skills if os.path.exists(os.path.join(HOME, ".claude", "skills", s))]
    check(len(linked) == len(skills), f"skills linked for Claude ({len(linked)}/{len(skills)})", "run scripts/install.py")

    print("Hooks")
    g = " ".join(commands(load(os.path.join(HOME, ".claude", "settings.json"))))
    for script in ("guard_dangerous.py", "mcp_health.py", "usage_tracker.py", "notify_done.py", "auto_allow_reads.py"):
        check(script in g, f"global: {script}", "run scripts/install.py")
    v = " ".join(commands(load(os.path.join(vault, ".claude", "settings.json"))))
    for script, label in (("session_context.sh", "session context"), ("inbox_nudge.sh", "inbox nudge"), ("inject --me claude", "agent-sync"),
                          ("archive_now.sh", "session archive"), ("update_hot.py", "hot.md refresh after /compact")):
        check(script in v, f"vault: {label}", "run scripts/install.py")
    c = " ".join(commands(load(os.path.join(vault, ".codex", "hooks.json"))))
    check("--me codex" in c, "Codex: agent-sync", "run scripts/install.py, then in Codex: /hooks, press t")

    print("Vault search")
    servers = load(os.path.join(vault, ".mcp.json")).get("mcpServers", {})
    check(all(s in servers for s in ("vault-rag", "vault-graph", "vault-router")), "MCP servers registered", "run scripts/install.py")
    venv = os.path.join(HOME, ".ecx", "venv", "bin", "python")
    if not os.path.exists(venv):
        warn("search stack not installed", "optional: python3 scripts/install.py --with-search")
    else:
        for name, sub in (("meaning index (ChromaDB)", "chroma_db"), ("relationship graph (LightRAG)", "lightrag_db")):
            age = age_days(os.path.join(DATA, sub))
            check(age is not None and age < 2, f"{name}" + (f", updated {age:.1f} days ago" if age is not None else ", never built"),
                  "run the matching vault-search/*ingest.py, and check its log in ~/.ecx/index")
        ollama = port_open(11434)
        check(ollama, "Ollama running (needed by the graph)", "open the Ollama app, or `ollama serve`")
        if ollama:
            try:
                tags = json.loads(subprocess.run(["curl", "-s", "-m", "3", "localhost:11434/api/tags"], capture_output=True, text=True).stdout)
                names = {m["name"].split(":")[0] for m in tags.get("models", [])}
                check("nomic-embed-text" in names, "embedding model pulled", "ollama pull nomic-embed-text")
            except Exception:
                warn("could not list Ollama models", "run: ollama list")

    print("Nightly jobs")
    cron = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    if "vault-search/ingest.py" in cron:
        check(True, "nightly re-index scheduled")
    else:
        warn("nightly re-index not scheduled", "optional: python3 scripts/install.py --with-cron")
    for log in ("ingest.log", "lightrag.log"):
        p = os.path.join(DATA, log)
        if os.path.exists(p):
            tail = open(p, errors="ignore").read()[-4000:]
            bad = re.findall(r"(Operation not permitted|Traceback|WARNING: \d+ docs FAILED|Unauthorized)", tail)
            check(not bad, f"{log}: last run clean", f"last run hit '{bad[-1] if bad else ''}'; read {p}")

    print("Phone vault")
    remote = subprocess.run(["git", "-C", vault, "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
    if not remote:
        warn("no GitHub remote", "optional: push the vault to a PRIVATE repo, then install with --with-phone")
    else:
        check(True, f"remote: {remote}")
        if shutil.which("gh"):
            out = subprocess.run(["gh", "repo", "view", remote, "--json", "isPrivate", "-q", ".isPrivate"], capture_output=True, text=True).stdout.strip()
            check(out == "true", "vault repo is private", "make the vault repo private: it holds your notes")
        log = os.path.join(HOME, ".vault-sync", "sync.log")
        if os.path.exists(log):
            last = open(log).read().strip().splitlines()[-1:] or [""]
            check("CONFLICT" not in last[0] and "failed" not in last[0], f"last sync: {last[0][:60]}", f"read {log}")

    bad = results.count(False)
    print(f"\n{len(results) - bad}/{len(results)} checks passed" + ("" if not bad else f", {bad} to fix (see above)") + "\n")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
