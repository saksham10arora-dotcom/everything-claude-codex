#!/usr/bin/env python3
"""ECX installer. Safe to re-run: it adds what's missing, never overwrites your
files, and backs up every settings file it changes (*.ecx-bak).

    python3 scripts/install.py --vault ~/vault --name "Ada"
    python3 scripts/install.py --vault ~/vault --name "Ada" --with-search --with-cron --with-phone
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

ECX = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
PY = sys.executable
VAULT_DIRS = ["inbox", "daily", "projects", "personal", "research", "wiki", "content", "archive", ".remember", "agents"]


def say(sym, msg):
    print(f"  {sym} {msg}")


def memory_dir(vault):
    return os.path.join(HOME, ".claude", "projects", re.sub(r"[^A-Za-z0-9]", "-", os.path.realpath(vault)), "memory")


def render(path, out, values):
    if os.path.exists(out):
        say("=", f"{os.path.relpath(out, values['{{VAULT}}'])} exists, left as is")
        return
    s = open(path).read()
    for k, v in values.items():
        s = s.replace(k, v)
    with open(out, "w") as f:
        f.write(s)
    say("+", f"created {os.path.relpath(out, values['{{VAULT}}'])}")


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and not os.path.exists(path + ".ecx-bak"):
        shutil.copy(path, path + ".ecx-bak")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def add_hooks(cfg, event, command, matcher=None, timeout=10):
    """Add one command hook unless the same command is already there."""
    groups = cfg.setdefault("hooks", {}).setdefault(event, [])
    if any(h.get("command") == command for g in groups for h in g.get("hooks", [])):
        return False
    group = {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}
    if matcher:
        group["matcher"] = matcher
    groups.append(group)
    return True


def q(path):
    return f'"{path}"'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.path.join(HOME, "vault"))
    ap.add_argument("--name", default=os.environ.get("USER", "me"))
    ap.add_argument("--with-search", action="store_true", help="install the vault search stack (ChromaDB, LightRAG, CLIP) into ~/.ecx/venv")
    ap.add_argument("--with-cron", action="store_true", help="re-index the vault every evening")
    ap.add_argument("--with-phone", action="store_true", help="sync the vault to its GitHub remote after every reply")
    a = ap.parse_args()

    vault = os.path.realpath(os.path.expanduser(a.vault))
    data = os.path.join(HOME, ".ecx", "index")
    venv_py = os.path.join(HOME, ".ecx", "venv", "bin", "python")
    search_py = venv_py if os.path.exists(venv_py) or a.with_search else PY
    values = {"{{VAULT}}": vault, "{{NAME}}": a.name, "{{ECX}}": ECX,
              "{{MEMORY_DIR}}": memory_dir(vault), "{{DATE}}": datetime.date.today().isoformat()}
    env = {"ECX_VAULT": vault, "ECX_DATA": data, "AGENT_SYNC_USER": a.name}
    E = f"ECX_VAULT={q(vault)} ECX_DATA={q(data)} AGENT_SYNC_USER={q(a.name)}"   # passed explicitly to every vault hook

    print(f"\nECX: installing for {a.name}\n  vault: {vault}\n")

    # 1. Vault skeleton and templates (never overwrites)
    print("Vault")
    for d in VAULT_DIRS:
        os.makedirs(os.path.join(vault, d), exist_ok=True)
    render(os.path.join(ECX, "templates", "CLAUDE.md"), os.path.join(vault, "CLAUDE.md"), values)
    render(os.path.join(ECX, "templates", "AGENTS.md"), os.path.join(vault, "AGENTS.md"), values)
    render(os.path.join(ECX, "templates", "hot.md"), os.path.join(vault, ".remember", "hot.md"), values)

    # 2. Skills, linked for Claude Code and for Codex / other agents
    print("Skills")
    for target in (os.path.join(HOME, ".claude", "skills"), os.path.join(HOME, ".agents", "skills")):
        os.makedirs(target, exist_ok=True)
        added = 0
        for name in sorted(os.listdir(os.path.join(ECX, "skills"))):
            dst = os.path.join(target, name)
            if not os.path.exists(dst):
                os.symlink(os.path.join(ECX, "skills", name), dst)
                added += 1
        say("+", f"{added} skills linked into {target.replace(HOME, '~')}")

    # 3. Global hooks: work in every project
    print("Hooks")
    gpath = os.path.join(HOME, ".claude", "settings.json")
    g = load_json(gpath)
    h = os.path.join(ECX, "hooks")
    n = 0
    n += add_hooks(g, "PreToolUse", f"{PY} {q(h + '/guard_dangerous.py')}", "Bash", 5)
    n += add_hooks(g, "PreToolUse", f"{PY} {q(h + '/mcp_health.py')} pre", "^mcp__", 3)
    n += add_hooks(g, "PostToolUse", f"{PY} {q(h + '/mcp_health.py')} ok", "^mcp__", 3)
    n += add_hooks(g, "PostToolUseFailure", f"{PY} {q(h + '/mcp_health.py')} fail", "^mcp__", 3)
    n += add_hooks(g, "PermissionRequest", f"{PY} {q(h + '/auto_allow_reads.py')}", None, 3)
    n += add_hooks(g, "Stop", f"{PY} {q(h + '/usage_tracker.py')}", None, 15)
    n += add_hooks(g, "Stop", f"{PY} {q(h + '/notify_done.py')}", None, 8)
    if "statusLine" not in g:
        g["statusLine"] = {"type": "command", "command": f"bash {q(ECX + '/statusline/statusline.sh')}"}
        say("+", "status line: context bar + unread agent mail")
    save_json(gpath, g)
    say("+", f"{n} global hooks added to ~/.claude/settings.json")

    # 4. Vault hooks: memory, inbox, agent-sync, AI-tell guard
    vpath = os.path.join(vault, ".claude", "settings.json")
    v = load_json(vpath)
    v.setdefault("env", {}).update(env)
    n = 0
    n += add_hooks(v, "SessionStart", f"{E} bash {q(h + '/session_context.sh')}", None, 10)
    n += add_hooks(v, "SessionStart", f"{E} bash {q(h + '/inbox_nudge.sh')}", None, 10)
    n += add_hooks(v, "UserPromptSubmit", f"{E} {PY} {q(ECX + '/agent-sync/sync.py')} inject --me claude", None, 5)
    n += add_hooks(v, "PostToolUse", f"bash {q(h + '/ai_tell_guard.sh')}", "Write|Edit", 5)
    n += add_hooks(v, "Stop", f"{E} bash {q(h + '/archive_now.sh')}", None, 5)
    n += add_hooks(v, "PostCompact", f"{E} {PY} {q(ECX + '/memory/update_hot.py')}", None, 10)
    n += add_hooks(v, "Stop", f"{E} bash {q(ECX + '/phone-vault/remember_on_stop.sh')}", None, 5)
    if a.with_phone:
        n += add_hooks(v, "Stop", f"({E} nohup bash {q(ECX + '/phone-vault/sync.sh')} >/dev/null 2>&1 &)", None, 5)
    save_json(vpath, v)
    say("+", f"{n} vault hooks added to {vpath.replace(HOME, '~')}")

    # 5. Codex: same agent-sync hook (Codex asks you to trust new hooks once)
    cpath = os.path.join(vault, ".codex", "hooks.json")
    c = load_json(cpath)
    n = int(add_hooks(c, "UserPromptSubmit", f"{E} {PY} {q(ECX + '/agent-sync/sync.py')} inject --me codex", None, 5))
    if a.with_phone:
        n += add_hooks(c, "Stop", f"({E} nohup bash {q(ECX + '/phone-vault/sync.sh')} >/dev/null 2>&1 &)", None, 5)
    save_json(cpath, c)
    say("+", f"{n} Codex hooks added to .codex/hooks.json (approve them once: run `codex`, type /hooks, press t)")

    # agent mail renders to a markdown file you can read
    os.makedirs(os.path.join(HOME, ".agent-sync"), exist_ok=True)
    cfgp = os.path.join(HOME, ".agent-sync", "config.json")
    cfg = load_json(cfgp)
    cfg.setdefault("chat_md", os.path.join(vault, "agents", "AGENT_CHAT.md"))
    save_json(cfgp, cfg)

    # 6. Vault search MCP servers (vault-rag, vault-graph, vault-router)
    print("Vault search")
    mpath = os.path.join(vault, ".mcp.json")
    m = load_json(mpath)
    servers = m.setdefault("mcpServers", {})
    for name, script in (("vault-rag", "mcp_server.py"), ("vault-graph", "lightrag_mcp_server.py"), ("vault-router", "smart_router_mcp_server.py")):
        servers.setdefault(name, {"command": search_py, "args": [os.path.join(ECX, "vault-search", script)], "env": env})
    save_json(mpath, m)
    say("+", "3 MCP servers registered in .mcp.json")
    if a.with_search:
        venv = os.path.join(HOME, ".ecx", "venv")
        if not os.path.exists(venv_py):
            subprocess.run([PY, "-m", "venv", venv], check=True)
        subprocess.run([venv_py, "-m", "pip", "install", "-q", "-r", os.path.join(ECX, "vault-search", "requirements.txt")], check=True)
        say("+", "search stack installed in ~/.ecx/venv. Build the first index: "
                 f"ECX_VAULT={vault} {venv_py} {ECX}/vault-search/ingest.py")
    else:
        say("i", "search stack not installed (heavy). Re-run with --with-search when you want it.")

    # 7. Nightly jobs
    if a.with_cron:
        print("Nightly jobs")
        jobs = {
            "ingest.py": f"30 20 * * * ECX_VAULT={vault} ECX_DATA={data} {search_py} {ECX}/vault-search/ingest.py >> {data}/ingest.log 2>&1",
            "lightrag_ingest.py": f"0 21 * * * ECX_VAULT={vault} ECX_DATA={data} {search_py} {ECX}/vault-search/lightrag_ingest.py --folder research personal projects >> {data}/lightrag.log 2>&1",
            "multimodal_ingest.py": f"0 22 * * * ECX_VAULT={vault} ECX_DATA={data} {search_py} {ECX}/vault-search/multimodal_ingest.py >> {data}/images.log 2>&1",
            "tracker_staleness.py": f"0 9 * * * ECX_VAULT={vault} {PY} {ECX}/jobs/tracker_staleness.py >> {data}/staleness.log 2>&1",
        }
        os.makedirs(data, exist_ok=True)
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        new = [line for key, line in jobs.items() if f"{ECX}/" not in cur or key not in cur]
        if new:
            subprocess.run(["crontab", "-"], input=cur.rstrip("\n") + "\n" + "\n".join(new) + "\n", text=True, check=True)
        say("+", f"{len(new)} nightly jobs added (crontab -l to see them)")

    if a.with_phone:
        print("Phone vault")
        wf = os.path.join(vault, ".github", "workflows", "inbox-automerge.yml")
        os.makedirs(os.path.dirname(wf), exist_ok=True)
        if not os.path.exists(wf):
            shutil.copy(os.path.join(ECX, "phone-vault", "inbox-automerge.yml"), wf)
        say("+", "vault syncs to its GitHub remote after every reply; phone captures auto-merge into inbox/")
        say("i", "make sure the vault is a git repo with a PRIVATE GitHub remote before you rely on this")

    print(f"\nDone. Open Claude Code in {vault} and say: /boot\n"
          f"Check everything any time: python3 {ECX}/scripts/doctor.py --vault {vault}\n")


if __name__ == "__main__":
    main()
