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
    readable: list = field(default_factory=list)  # folders agents may cd into to read, never to change (the vault)

    def __post_init__(self):
        # agents report real paths (/private/var/...), the user may pass a symlinked one (/var/...)
        self.workdir = os.path.realpath(os.path.expanduser(self.workdir))
        self.existed = {os.path.realpath(p) for p in self.existed}
        self.created = {os.path.realpath(p) for p in self.created}
        self.readable = [os.path.realpath(os.path.expanduser(p)) for p in self.readable]

    def mark_created(self, path):
        self.created.add(os.path.realpath(path))


@dataclass
class Request:
    agent: str
    tool: str
    input: dict


OUTWARD = [  # card: sends, publishes, deploys or reaches another machine. Fail closed: over-matching is fine.
    (r"\bgit\b.*\bpush\b", "pushes to a remote"),
    (r"\bgh\s", "acts on GitHub"),
    (r"\bcurl\b.*(\s-X\s*(POST|PUT|PATCH|DELETE)|--request\s+(POST|PUT|PATCH|DELETE)|\s--data|\s-d|\s--json|\s-F|\s--form"
     r"|\s-T\s|--upload-file)", "sends data to the internet"),
    (r"\bwget\b.*--post", "sends data to the internet"),
    (r"\b(http|https|xh)\s+(POST|PUT|PATCH|DELETE)\b", "sends data to the internet"),
    (r"publish|deploy|release", "may publish, deploy or release something"),
    (r"\b(docker|podman)\b.*\bpush\b", "pushes an image"),
    (r"\b(vercel|netlify|firebase|flyctl|heroku|wrangler|gcloud|aws|az|twine)\b", "acts on a cloud service"),
    (r"\b(ssh|scp|rsync|sftp|nc|ncat|telnet|ftp)\b", "connects to another machine"),
    (r"(^|[;&|(]\s*)(sendmail|mail|mailx)\b", "sends an email"),
    (r"(\bnpm\s+(install|i)\b.*\s(-g|--global)\b)|\bbrew\s+install\b|\bsudo\s+pip\b|\bpip3?\s+install\b.*--user\b",
     "installs a global package"),
]
DESTRUCTIVE = [  # card: discards work, rewrites history, or switches the branch they work on
    (r"\bgit\b.*\b(clean|rebase|filter-branch|filter-repo|update-ref|restore|checkout|switch)\b",
     "can discard work, rewrite history or switch branches"),
    (r"\bgit\b.*\bstash\s+(drop|clear)\b", "throws away stashed work"),
    (r"\bgit\b.*\bbranch\b.*(\s-[dDmMfc]\b|--delete|--move|--force)", "deletes, moves or forces a branch"),
    (r"\bgit\b.*\bcommit\b.*(--amend|--all|\s-[a-zA-Z]*a[a-zA-Z]*\b)", "rewrites a commit or commits every change"),
    (r"\bgit\b.*\badd\b(.*\s)?(-A\b|--all\b|-u\b|\.(\s|$))", "stages every file, including yours"),
    (r"\bgit\b.*\bconfig\b.*--(global|system)\b", "changes your global git settings"),
    (r"\bfind\b.*\s-(delete|exec|execdir|ok)\b", "can delete or change many files"),
    (r"\b(truncate|unlink|shred|srm)\b", "destroys file contents"),
    (r"\b(python3?|node|perl|ruby|bun|deno)\b\s+(-c|-e|--eval)\b.*(remove|unlink|rmtree|rmdir|rename|replace|truncate|"
     r"system|subprocess|spawn|exec|urlopen|requests|fetch|http|socket|writeFile|open\()", "runs inline code that can "
     "change files or reach the network"),
]
READ_ONLY = ("cd", "ls", "cat", "head", "tail", "wc", "grep", "rg", "git status", "git log", "git diff", "git show",
             "git ls-files", "git rev-parse", "git blame", "git grep", "du", "df", "date", "uname",
             "pwd", "echo", "tree", "which", "python --version", "python3 --version", "node --version", "file", "stat")
READ_VERBS = re.compile(r"^(get|list|search|read|fetch|query|find|describe|status|whoami|lookup|count|check|health|"
                        r"recall|view|show|explain|path|smart_search|graph_search)", re.I)
CLAUDE_SAFE = {"Task", "Agent", "TodoWrite", "TodoRead", "ToolSearch", "Skill", "LSP", "EnterPlanMode", "ExitPlanMode",
               "BashOutput", "KillShell", "KillBash", "web"}
WRAPPER = re.compile(r"^\s*(/bin/|/usr/bin/)?(ba|z)?sh\s+-l?c\s+(?P<q>['\"])(?P<body>.*)(?P=q)\s*$", re.S)
BARE_WRAPPER = re.compile(r"^\s*(/bin/|/usr/bin/)?(ba|z)?sh\s+-l?c\s+(?P<body>[^'\"\s][^\s]*)\s*$")


def unwrap(cmd):
    """Codex runs everything as `/bin/zsh -lc "<command>"`; judge the inner command."""
    m = WRAPPER.match(cmd or "")
    if m:
        return m.group("body").replace('\\"', '"')
    m = BARE_WRAPPER.match(cmd or "")
    return m.group("body") if m else (cmd or "")


def _abs(path, ctx):
    p = os.path.expanduser(path or "")
    return os.path.realpath(p if os.path.isabs(p) else os.path.join(ctx.workdir, p))


def _inside(path, root):
    root = os.path.realpath(os.path.expanduser(root))
    return path == root or path.startswith(root + os.sep)


def _touches_protected(text, ctx):
    low = text.lower()
    home = os.path.expanduser("~")
    for p in ctx.protected:
        p = os.path.normpath(os.path.expanduser(p))
        parent = os.path.dirname(p)
        for base in {p, p.replace(home, "~", 1), p.replace(home, "$HOME", 1)}:
            if base.lower() in low:
                return True
        for par in {parent, parent.replace(home, "~", 1), parent.replace(home, "$HOME", 1)}:
            # a glob in the protected folder's parent can reach it (ls ~/Downloads/y*)
            if re.search(re.escape(par.lower()) + r"/[^\s/]*[*?\[]", low):
                return True
    return False


def _existed(p, ctx):
    """Was there before this run: in the start snapshot, or on disk now and not made by the agents (covers ignored
    files like .env that the snapshot never saw)."""
    return (p in ctx.existed or os.path.lexists(p)) and p not in ctx.created


def _words(cmd):
    try:
        return shlex.split(cmd, posix=True)
    except ValueError:
        return None


SEPARATORS = {"&&", ";", "||", "|", "&"}


def _args_of(words, names):
    """[(command, [args])] for every use of one of `names` in a command chain (git rm counts as rm)."""
    out, i = [], 0
    while i < len(words):
        w = words[i]
        name = None
        if w in names:
            name, i = w, i + 1
        elif w == "git" and i + 1 < len(words) and words[i + 1] in names:
            name, i = words[i + 1], i + 2
        if name:
            args = []
            while i < len(words) and words[i] not in SEPARATORS:
                args.append(words[i])
                i += 1
            out.append((name, args))
        i += 1
    return out


def _risky_target(t, ctx):
    if any(ch in t for ch in "$~`*?[") or t.startswith("-"):
        return True
    p = _abs(t, ctx)
    return not _inside(p, ctx.workdir) or os.path.isdir(p) or _existed(p, ctx)


def _structure(cmd, ctx):
    """Card reasons that need the command's shape, not just a pattern."""
    words_src = cmd
    cmd = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", '""', cmd)  # quoted text is data: a ">" in a message is not a redirect
    reads_elsewhere = False
    for m in re.finditer(r"(?:^|[;&|(]\s*)cd(?:\s+([^\s;&|)]+))?", cmd):
        t = m.group(1)
        if not t or any(ch in t for ch in "$`"):
            return "changes directory out of the work folder"
        p = _abs(t, ctx)
        if _inside(p, ctx.workdir):
            continue
        if any(_inside(p, r) for r in ctx.readable):
            reads_elsewhere = True  # fine only if everything in the command just reads
            continue
        return "changes directory out of the work folder"
    if reads_elsewhere and not _read_only(words_src, ctx):
        return "goes into a read-only folder (your vault) and may change something there"
    for m in re.finditer(r"(?<![<\d&])(>>?)\s*([^\s;&|)]+)", cmd):
        t = m.group(2).strip("'\"")
        if t in ("/dev/null", "/dev/stderr", "/dev/stdout") or t.startswith("&"):
            continue
        p = _abs(t, ctx)
        if any(ch in t for ch in "$`") or not _inside(p, ctx.workdir):
            return f"writes to {t}, outside the work folder"
        if m.group(1) == ">" and _existed(p, ctx):
            return f"overwrites {t}, which was there before this run"
    for m in re.finditer(r"\btee\s+((?:-\S+\s+)*)([^\s;&|)]+)", cmd):
        p = _abs(m.group(2), ctx)
        if not _inside(p, ctx.workdir) or ("-a" not in m.group(1) and _existed(p, ctx)):
            return f"writes to {m.group(2)} with tee"
    words = _words(words_src)
    if words is None:
        return "has quoting duo cannot read"
    for name, args in _args_of(words, {"rm", "mv"}):
        files = [a for a in args if not a.startswith("-")]
        if name == "rm":
            if not files or any("r" in a.lower() for a in args if a.startswith("-") and not a.startswith("--")) \
                    or "--recursive" in args:
                return "deletes a folder or unnamed files"
            for t in files:
                if _risky_target(t, ctx):
                    return f"deletes {t}, which was there before this run (or is outside the work folder)"
        else:
            if len(files) < 2:
                return "moves files"
            for t in files[:-1]:
                if _risky_target(t, ctx):
                    return f"moves {t}, which was there before this run"
            dest = _abs(files[-1], ctx)
            if not _inside(dest, ctx.workdir) or (os.path.lexists(dest) and not os.path.isdir(dest) and _existed(dest, ctx)):
                return f"moves files to {files[-1]}"
    return None


TESTS = ("pytest", "python -m pytest", "python3 -m pytest", "python -m unittest", "python3 -m unittest", "npm test",
         "npm run test", "yarn test", "pnpm test", "cargo test", "go test", "make test", "bun test")
SAFE_PIPE_TARGETS = ("head", "tail", "wc", "grep", "rg", "uniq", "cut", "cat", "less", "awk", "sed -n", "tr")
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
    if re.search(r">|`|\$\(|\btee\b|\bsed\s+-i|\s-o\s|--output", c):
        return False
    for part in re.split(r"&&|\|\||;|\||&|\n", c):
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
    for rx, what in OUTWARD + DESTRUCTIVE:
        if re.search(rx, cmd, re.I):
            return "card", f"This command {what}."
    shape = _structure(cmd, ctx)
    if shape:
        return "card", f"This command {shape}."
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
    if t == "delete" and _existed(p, ctx):
        return "card", f"This deletes {os.path.relpath(p, ctx.workdir)}, which was there before this run."
    if t == "write" and _existed(p, ctx):
        return "card", f"This replaces {os.path.relpath(p, ctx.workdir)} wholesale."
    return "allow", ""


def classify(req, ctx):
    """-> ("allow" | "card" | "block", reason). Anything duo does not recognise as safe gets a card."""
    blob = " ".join(str(v) for v in req.input.values())
    if _touches_protected(blob, ctx):
        return "block", "That path is protected. Agents never touch it."
    if req.tool == "bash":
        return _bash(req, ctx)
    if req.tool in ("write", "edit", "delete", "read"):
        return _file(req, ctx)
    if req.tool == "mcp" or req.tool.startswith("mcp__"):
        name = req.input.get("name") or req.tool
        last = re.split(r"__|\.|/", name)[-1]
        if READ_VERBS.match(last):
            return "allow", ""
        return "card", f"The tool {name} may act outside this folder (send, post, click, change or schedule)."
    if req.tool in CLAUDE_SAFE:
        return "allow", ""
    return "card", f"duo does not know the tool {req.tool}, so it asks first."
