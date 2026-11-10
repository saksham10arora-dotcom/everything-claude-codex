"""One rule book for every permission request from either agent: allow, approval card, or block."""
import importlib.util
import os
import re
import shlex
from dataclasses import dataclass, field

_GUARD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "guard_dangerous.py")
_spec = importlib.util.spec_from_file_location("ecx_guard_dangerous", _GUARD)
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


@dataclass
class Ctx:
    workdir: str
    phase: str = "plan"  # "plan" | "build"
    existed: set = field(default_factory=set)
    created: set = field(default_factory=set)
    protected: list = field(default_factory=list)

    def __post_init__(self):
        # agents report real paths (/private/var/...), the user may pass a symlinked one (/var/...)
        self.workdir = os.path.realpath(os.path.expanduser(self.workdir))
        self.existed = {os.path.realpath(p) for p in self.existed}
        self.created = {os.path.realpath(p) for p in self.created}

    def mark_created(self, path):
        self.created.add(os.path.realpath(path))


@dataclass
class Request:
    agent: str
    tool: str
    input: dict


OUTWARD = [
    (r"\bgit\s+push\b", "pushes to a remote"),
    (r"\bgh\s", "acts on GitHub"),
    (r"\bcurl\b.*(-X\s*(POST|PUT|PATCH|DELETE)|--request\s+(POST|PUT|PATCH|DELETE)|--data|-d\s|-F\s|--form|-T\s|--upload-file)",
     "sends data to the internet"),
    (r"\bwget\b.*--post", "sends data to the internet"),
    (r"\bnpm\s+publish\b|\byarn\s+publish\b|\bcargo\s+publish\b", "publishes a package"),
    (r"\bvercel\b|\bnetlify\b|\bfly\s+deploy\b|\bfirebase\s+deploy\b", "deploys"),
    (r"\btwine\s+upload\b", "publishes a package"),
    (r"\b(ssh|scp|rsync|sftp)\b.*@", "connects to another machine"),
    (r"\b(sendmail|mail|mailx)\b\s", "sends an email"),
    (r"(\bnpm\s+(install|i)\b.*\s(-g|--global)\b)|\bbrew\s+install\b|\bsudo\s+pip\b|\bpip3?\s+install\b.*--user\b",
     "installs a global package"),
]
READ_ONLY = ("ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "git status", "git log", "git diff", "git show", "git ls-files", "git branch", "git rev-parse",
             "git blame", "git grep", "du", "df", "date", "uname",
             "pwd", "echo", "tree", "which", "python --version", "python3 --version", "node --version", "file", "stat")
MCP_ACTS = re.compile(r"(send|reply|post|publish|create|delete|update|forward|trash|upload|share|respond|merge|push|fork|"
                      r"comment|label|spam|draft|schedule|book|pay|transfer|submit|click|type|navigate|fill|form|"
                      r"computer|run|execute|write|edit|remove|move|rename|set|add|invite|archive)", re.I)
WRAPPER = re.compile(r"^\s*(/bin/|/usr/bin/)?(ba|z)?sh\s+-l?c\s+(?P<q>['\"])(?P<body>.*)(?P=q)\s*$", re.S)


def unwrap(cmd):
    """Codex runs everything as `/bin/zsh -lc "<command>"`; judge the inner command."""
    m = WRAPPER.match(cmd or "")
    return m.group("body").replace('\\"', '"') if m else (cmd or "")


def _abs(path, ctx):
    p = os.path.expanduser(path or "")
    return os.path.realpath(p if os.path.isabs(p) else os.path.join(ctx.workdir, p))


def _inside(path, root):
    root = os.path.realpath(os.path.expanduser(root))
    return path == root or path.startswith(root + os.sep)


def _touches_protected(text, ctx):
    for p in ctx.protected:
        p = os.path.normpath(os.path.expanduser(p))
        home = os.path.expanduser("~")
        variants = {p, p.replace(home, "~", 1), p.replace(home, "$HOME", 1)}
        if any(v in text for v in variants):
            return True
    return False


def _rm_targets(cmd):
    try:
        words = shlex.split(cmd)
    except ValueError:
        return None
    out, i = [], 0
    while i < len(words):
        w = words[i]
        if w == "rm" or (w == "git" and i + 1 < len(words) and words[i + 1] == "rm"):
            i += 2 if w == "git" else 1
            while i < len(words) and words[i] not in ("&&", ";", "||", "|"):
                if not words[i].startswith("-"):
                    out.append(words[i])
                elif "r" in words[i].lstrip("-") or "R" in words[i]:
                    out.append("<recursive>")
                i += 1
        i += 1
    return out


TESTS = ("pytest", "python -m pytest", "python3 -m pytest", "python -m unittest", "python3 -m unittest", "npm test",
         "npm run test", "yarn test", "pnpm test", "cargo test", "go test", "make test", "bun test")
SAFE_PIPE_TARGETS = ("head", "tail", "wc", "grep", "rg", "sort", "uniq", "cut", "cat", "less", "awk", "sed -n", "tr")


ENV_PREFIX = re.compile(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+")


def _read_only(cmd, ctx):
    """True when every piece of a command chain only reads, runs the tests, or writes into the run folder."""
    c = cmd.split("\n", 1)[0] if "<<" in cmd else cmd  # a heredoc body is data, not commands
    c = re.sub(r"\s[12]?>\s*/dev/null|\s2>&1", " ", c)
    run_folder = os.path.join(ctx.workdir, ".duo")
    for m in list(re.finditer(r"(?<![<\d&])>>?\s*([^\s;&|]+)", c)):
        if not _inside(_abs(m.group(1).strip("'\""), ctx), run_folder):
            return False
        c = c.replace(m.group(0), " ")
    if re.search(r">|`|\$\(|\btee\b|\bsed\s+-i", c):
        return False
    for part in re.split(r"&&|\|\||;|\|", c):
        p = ENV_PREFIX.sub("", part.strip().strip("()").strip())
        if not p:
            continue
        if not any(p == r or p.startswith(r + " ") for r in READ_ONLY + TESTS + SAFE_PIPE_TARGETS):
            return False
    return True


def _bash(req, ctx):
    cmd = ENV_PREFIX.sub("", unwrap(req.input.get("command", "")))
    decision, why = guard.decide(cmd)
    if decision == "deny":
        return "block", why
    if decision == "ask":
        return "card", why
    for rx, what in OUTWARD:
        if re.search(rx, cmd, re.I):
            return "card", f"This command {what}."
    if re.search(r"\b(rm|git\s+rm)\b", cmd):
        targets = _rm_targets(cmd)
        if targets is None or not targets:
            return "card", "This command deletes files."
        for t in targets:
            p = _abs(t, ctx)
            if t == "<recursive>" or any(ch in t for ch in "*?[") or p in ctx.existed or os.path.isdir(p) \
                    or not _inside(p, ctx.workdir):
                return "card", f"This command deletes {t if t != '<recursive>' else 'a folder'}, which was there before this run."
    if ctx.phase == "plan" and not _read_only(cmd, ctx):
        return "card", "The plan is not approved yet, and this command may change things."
    return "allow", ""


def _file(req, ctx):
    p = _abs(req.input.get("path", ""), ctx)
    t = req.tool
    if t == "read":
        return "allow", ""
    run_folder = os.path.join(ctx.workdir, ".duo")
    if ctx.phase == "plan" and not _inside(p, run_folder):
        return "block", "The plan is not approved yet. Write notes in the run folder."
    if not _inside(p, ctx.workdir):
        return "card", f"This changes {p}, outside the work folder."
    if t == "delete" and p in ctx.existed:
        return "card", f"This deletes {os.path.relpath(p, ctx.workdir)}, which was there before this run."
    if t == "write" and p in ctx.existed and p not in ctx.created:
        return "card", f"This replaces {os.path.relpath(p, ctx.workdir)} wholesale."
    return "allow", ""


def classify(req, ctx):
    """-> ("allow" | "card" | "block", reason)"""
    blob = " ".join(str(v) for v in req.input.values())
    if _touches_protected(blob, ctx) or _touches_protected(str(req.input.get("args", "")), ctx):
        return "block", "That path is protected. Agents never touch it."
    if req.tool == "bash":
        return _bash(req, ctx)
    if req.tool in ("write", "edit", "delete", "read"):
        return _file(req, ctx)
    if req.tool == "mcp" or req.tool.startswith("mcp__"):
        name = req.input.get("name") or req.tool
        last = re.split(r"__|\.|/", name)[-1]
        if MCP_ACTS.search(last):
            return "card", f"The tool {name} can act outside this folder (send, publish, change or click)."
        return "allow", ""
    return "allow", ""
