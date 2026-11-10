"""What each duo agent knows at start: the brief, the user's context files, and a read-only agent-sync catch-up."""
import glob
import importlib.util
import os
from datetime import datetime, timedelta, timezone

_SYNC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "agent-sync", "sync.py")


def _sync():
    """Fresh import each call: agent-sync reads HOME at import time. Only its readers are used, never inject()."""
    spec = importlib.util.spec_from_file_location("ecx_agent_sync_ro", _SYNC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def context_files():
    env = os.environ.get("ECX_DUO_CONTEXT")
    if env is not None:
        paths = [p for p in env.split(":") if p]
    else:
        vault = os.environ.get("ECX_VAULT", "")
        paths = []
        if vault:
            paths += [os.path.join(vault, ".remember", "hot.md"), os.path.join(vault, ".remember", "recent.md")]
            slug = os.path.abspath(vault).replace("/", "-")
            paths.append(os.path.expanduser(f"~/.claude/projects/{slug}/memory/MEMORY.md"))
    return [os.path.expanduser(p) for p in paths if os.path.isfile(os.path.expanduser(p))]


def catchup(hours=6, limit_chars=12000):
    sync = _sync()
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    turns = []
    for pattern, is_codex, who in ((sync.CLAUDE_GLOB, False, "Claude"), (sync.CODEX_GLOB, True, "Codex")):
        for path in glob.glob(pattern):
            try:
                if os.path.getmtime(path) < since.timestamp():
                    continue
                found, _ = sync.read_new(path, 0, since, is_codex)
            except OSError:
                continue
            for t in found:
                if t["text"].startswith("This session is being continued"):
                    continue  # compaction summaries are huge and say nothing new
                speaker = "User" if t["role"] == "user" else who
                turns.append((t["dt"], f"[{speaker}, {who} session] {t['text'][:600]}"))
    turns.sort(key=lambda x: x[0])
    lines, size = [], 0
    for _, line in reversed(turns):  # keep the newest
        if size + len(line) + 1 > limit_chars:
            break
        lines.append(line)
        size += len(line) + 1
    return "\n".join(reversed(lines))


def brief(me, other, goal, user, run_dir):
    plan, summary = os.path.join(run_dir, "plan.md"), os.path.join(run_dir, "summary.md")
    parts = [f"""You are {me}. You are working with {other}, another AI, on one goal for {user}. You both work for {user}.

GOAL: {goal}

How to work together:
- Judge every decision by what is best for {user}, not by what keeps the peace.
- Challenge each other. If you think {other} is wrong, say so plainly and argue why. Never agree just to agree.
  Agree only when you are genuinely convinced, or when evidence settles it (a test passes, a number is better,
  the docs say so).
- Nobody is in charge. Decide between you how to split the work. Before you edit something, say what you are
  taking so you never both change the same thing.
- Messages from {other} arrive prefixed [{other}]. Messages from {user} arrive prefixed [{user} to you] or
  [{user} to both]. A message from {user} is an instruction from the boss.
- To talk to {other}, just write your message as normal text in your reply. duo delivers everything you write to
  {other} and shows it to {user}. Do not use any messaging, mail or agent tool to reach {other}.
- Keep messages to {other} short and concrete. Do the work, then talk about what you found.

Phases:
1. Plan first. Together, write one joint plan as a markdown checklist in {plan}. Where you still disagree, write
   both positions plainly. Do not change the project during planning; reading and running read-only commands is
   fine. When you think the plan is ready for {user}, say [[READY: plan]].
2. After {user} approves the plan, build it. If the plan needs a big change, update {plan} and say [[READY: plan]]
   again for a new approval.
3. Finish: when you think the goal is done, make sure {summary} exists with: what was built (commits and files),
   where you disagreed and how it was settled (or that it was not), what is still open, and what {user} should
   do next. Then say [[READY: done]]. It is finished only when you both say it.

Rules:
- Deleting or replacing existing files, destructive git commands, git push, publishing, deploying, opening PRs,
  sending any message or email, spending money, and installing global packages all pause for {user}'s approval.
  That is expected; ask, and if denied, find another way or move on.
- Commit only the files you changed, with git add <paths>. Never use git add -A or git add . .
- Everything you do is logged and shown to {user}."""]
    files = context_files()
    if files:
        parts.append(f"\n## What you know about {user} (their own context files)\n")
        for p in files:
            try:
                parts.append(f"### {p}\n{open(p).read()[:20000]}")
            except OSError:
                pass
    recent = catchup()
    if recent:
        parts.append(f"\n## {user}'s recent normal Claude and Codex sessions (read-only catch-up)\n{recent}")
    return "\n".join(parts)
