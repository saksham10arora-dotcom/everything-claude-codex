#!/usr/bin/env python3
"""
catchup.py: read full Claude Code session transcripts for cross-surface continuity.

Both the terminal CLI and the desktop "Code" tab write every session as a .jsonl
into ~/.claude/projects/<vault>/. This reads them back, full fidelity, so the
Claude you're talking to now can see what you did in the other surface.

Usage:
  python3 catchup.py            # full text of the most recent OTHER session
  python3 catchup.py list       # table of recent sessions (no bodies)
  python3 catchup.py 3          # full text of the last 3 other sessions
  python3 catchup.py all        # full text of every past session (heavy)
  python3 catchup.py <keyword>  # full text of past sessions mentioning <keyword>
"""
import sys, os, re, json, glob, time

# Claude Code stores each project's chats under ~/.claude/projects/<path with / -> ->.
# Match the vault and anything opened inside it (e.g. vault/site).
_VAULT = os.path.realpath(os.path.expanduser(os.environ.get("ECX_VAULT", "~/vault")))
PROJECT_GLOB = os.path.expanduser("~/.claude/projects/" + re.sub(r"[^A-Za-z0-9]", "-", _VAULT) + "*")
LIVE_WINDOW = 120  # files modified within this many seconds are the current/live session


def all_transcripts():
    files = []
    for d in glob.glob(PROJECT_GLOB):
        files.extend(glob.glob(os.path.join(d, "*.jsonl")))
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return files


def is_live(f):
    return (time.time() - os.path.getmtime(f)) < LIVE_WINDOW


def clean(t):
    t = t.strip()
    if not t:
        return None
    low = t.lower()
    if t.startswith("<") and ("system-reminder" in low or "command-" in low or "local-command" in low):
        return None
    if "Base directory for this skill" in t:
        return "[ran a /skill]"
    if "Caveat: The messages below" in t:
        return None
    return t


def messages(path):
    """Yield (who, text) for every real human/assistant message in a transcript."""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return
    for line in lines:
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        typ = o.get("type")
        if typ not in ("user", "assistant"):
            continue
        c = o.get("message", {}).get("content")
        txt = None
        if isinstance(c, str):
            txt = clean(c)
        elif isinstance(c, list):
            parts = [x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text"]
            txt = clean("\n".join(parts)) if parts else None
        if txt:
            yield ("YOU" if typ == "user" else "OTHER-CLAUDE", txt)


def first_user_line(path):
    for who, txt in messages(path):
        if who == "YOU":
            return txt.replace("\n", " ")[:90]
    return "(no text)"


def stamp(path):
    return time.strftime("%b %d %H:%M", time.localtime(os.path.getmtime(path)))


def print_list(files):
    print(f"Found {len(files)} past session(s) in this vault:\n")
    for i, f in enumerate(files, 1):
        n = sum(1 for _ in messages(f))
        print(f"  {i:>2}. {stamp(f)}  ({n:>3} msgs)  {first_user_line(f)}")
    print("\nRun `/catchup <n>` to read the last n in full, or `/catchup all`.")


def dump(files):
    for f in files:
        print(f"\n{'='*70}\nSESSION  {stamp(f)} :  {os.path.basename(f)}\n{'='*70}")
        for who, txt in messages(f):
            print(f"\n--- {who} ---\n{txt}")


def main():
    arg = sys.argv[1].strip().lower() if len(sys.argv) > 1 else "latest"
    files = all_transcripts()
    # The session you typed /catchup into is ALWAYS the most-recently-written
    # file at this instant, so drop exactly that one. (Don't time-window it -
    # a second open surface also looks "recent" and would be wrongly skipped.)
    others = files[1:]

    if not others:
        print("No other sessions found yet for this vault.")
        return

    if arg == "list":
        print_list(others)
    elif arg == "all":
        dump(others)
    elif arg.isdigit():
        dump(others[: int(arg)])
    elif arg in ("latest", ""):
        dump(others[:1])
    else:  # keyword search
        hits = [f for f in others if arg in open(f, encoding="utf-8", errors="ignore").read().lower()]
        if not hits:
            print(f"No past session mentions '{arg}'.")
            return
        print(f"{len(hits)} session(s) mention '{arg}':")
        dump(hits)


if __name__ == "__main__":
    main()
