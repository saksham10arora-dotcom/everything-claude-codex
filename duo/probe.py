#!/usr/bin/env python3
"""Probe the two CLIs exactly as duo drives them and record every raw frame.

    python3 duo/probe.py claude     -> tests/fixtures/duo/claude_probe.jsonl
    python3 duo/probe.py codex      -> tests/fixtures/duo/codex_probe.jsonl

Rerun when Claude Code or Codex updates; compare with duo/PROTOCOL.md.
Uses small prompts and a cheap Claude model, in a throwaway git repo.
"""
import glob
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "duo")


class Proc:
    """A child process speaking JSON lines; every frame both ways is recorded."""

    def __init__(self, cmd, cwd, out_path):
        self.p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True, bufsize=1)
        self.q = queue.Queue()
        self.rec = open(out_path, "w")
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=self._err, daemon=True).start()

    def _pump(self):
        for line in self.p.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                obj = {"_raw": line}
            self.rec.write(json.dumps({"dir": "in", "frame": obj}) + "\n"); self.rec.flush()
            self.q.put(obj)
        self.q.put(None)

    def _err(self):
        for line in self.p.stderr:
            self.rec.write(json.dumps({"dir": "stderr", "frame": line.rstrip()}) + "\n"); self.rec.flush()

    def send(self, obj):
        self.rec.write(json.dumps({"dir": "out", "frame": obj}) + "\n"); self.rec.flush()
        self.p.stdin.write(json.dumps(obj) + "\n"); self.p.stdin.flush()

    def get(self, timeout=180):
        return self.q.get(timeout=timeout)

    def close(self):
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.p.kill()
        self.rec.close()


def tmp_repo():
    d = tempfile.mkdtemp(prefix="duo-probe-")
    subprocess.run(["git", "init", "-q", d], check=True)
    open(os.path.join(d, "README.md"), "w").write("probe\n")
    subprocess.run(["git", "-C", d, "add", "."], check=True)
    subprocess.run(["git", "-C", d, "-c", "user.name=p", "-c", "user.email=p@p", "commit", "-qm", "init"], check=True)
    return d


def snapshot(pattern):
    return set(glob.glob(os.path.expanduser(pattern), recursive=True))


# ---------------------------------------------------------------- Claude
CLAUDE_CMD = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
              "--permission-mode", "default", "--permission-prompts", "host", "--permission-prompt-tool", "stdio", "--no-session-persistence",
              "--settings", json.dumps({"disableAllHooks": True}), "--model", "haiku"]


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def claude():
    d = tmp_repo()
    before = snapshot("~/.claude/projects/**/*.jsonl")
    p = Proc(CLAUDE_CMD, d, os.path.join(FIX, "claude_probe.jsonl"))
    notes = []
    p.send({"type": "control_request", "request_id": "init-1", "request": {"subtype": "initialize"}})
    p.send(user("Create a file a.txt containing the word hi, using the Write tool. Then reply DONE1."))
    phase, sent_mid, interrupted = 1, False, False
    deadline = time.time() + 300
    while time.time() < deadline:
        f = p.get()
        if f is None:
            notes.append("process exited"); break
        t = f.get("type")
        if t == "control_request" and f.get("request", {}).get("subtype") == "can_use_tool":
            r = f["request"]
            notes.append(f"can_use_tool phase{phase}: {r.get('tool_name')}")
            if phase == 1 and not sent_mid:
                sent_mid = True  # a user message while a permission request is pending
                p.send(user("(mid-turn note) After DONE1, also say MIDSEEN."))
            if phase == 2:
                resp = {"behavior": "deny", "message": "Denied by probe."}
            else:
                resp = {"behavior": "allow", "updatedInput": r.get("input", {})}
            p.send({"type": "control_response", "response": {"subtype": "success", "request_id": f["request_id"],
                                                              "response": resp}})
        elif t == "result":
            notes.append(f"result phase{phase}: {str(f.get('result'))[:80]}")
            if phase == 1:
                phase = 2
                p.send(user("Run the shell command `ls` with Bash and tell me the output."))
            elif phase == 2:
                phase = 3
                p.send(user("Run the shell command `sleep 30 && echo slept` with Bash."))
            elif phase == 3 or interrupted:
                break
        elif t == "assistant" and phase == 3 and not interrupted:
            pass
        if phase == 3 and not interrupted and t == "control_request":
            pass
        if phase == 3 and not interrupted and t in ("assistant", "stream_event", "control_request"):
            interrupted = True
            time.sleep(1)
            p.send({"type": "control_request", "request_id": "int-1", "request": {"subtype": "interrupt"}})
            notes.append("sent interrupt")
    p.close()
    after = snapshot("~/.claude/projects/**/*.jsonl")
    notes.append(f"new claude transcript files: {sorted(after - before)}")
    notes.append(f"a.txt exists: {os.path.exists(os.path.join(d, 'a.txt'))}")
    print("\n".join(notes))


# ---------------------------------------------------------------- Codex
class Rpc(Proc):
    def __init__(self, *a):
        super().__init__(*a)
        self.n = 0
        self.pending = []

    def call(self, method, params, wait=True):
        self.n += 1
        self.send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        if not wait:
            return self.n
        rid = self.n
        while True:
            f = self.get()
            if f is None:
                raise RuntimeError("app-server exited")
            if f.get("id") == rid and "method" not in f:
                return f
            self.pending.append(f)

    def next(self, timeout=180):
        return self.pending.pop(0) if self.pending else self.get(timeout)


def codex():
    d = tmp_repo()
    before = snapshot("~/.codex/sessions/**/*.jsonl")
    # duo-only Codex home: shares login, config and AGENTS.md, not the user's allow-rules or history
    home = os.path.join(tempfile.gettempdir(), "duo-probe-codex-home")
    os.makedirs(home, exist_ok=True)
    for f in ("auth.json", "config.toml", "AGENTS.md", "skills"):
        src, dst = os.path.expanduser(f"~/.codex/{f}"), os.path.join(home, f)
        if os.path.exists(src) and not os.path.lexists(dst):
            os.symlink(src, dst)
    os.environ["CODEX_HOME"] = home
    servers = [ln.strip()[len("[mcp_servers."):-1] for ln in open(os.path.expanduser("~/.codex/config.toml"))
               if ln.strip().startswith("[mcp_servers.") and ln.strip().count(".") == 1]
    cmd = ["codex", "app-server", "-c", "features.codex_hooks=false"]
    for s in servers:
        cmd += ["-c", f'mcp_servers.{s}.default_tools_approval_mode="prompt"']
    p = Rpc(cmd, d, os.path.join(FIX, "codex_probe.jsonl"))
    notes = []
    r = p.call("initialize", {"clientInfo": {"name": "ecx-duo-probe", "version": "0.1"}})
    notes.append(f"initialize: {json.dumps(r)[:200]}")
    p.send({"jsonrpc": "2.0", "method": "initialized"})
    r = p.call("thread/start", {"cwd": d, "ephemeral": True, "approvalPolicy": "untrusted", "sandbox": "read-only"})
    notes.append(f"thread/start: {json.dumps(r)[:300]}")
    tid = r.get("result", {}).get("thread", {}).get("id")

    def turn(text, **kw):
        r = p.call("turn/start", {"threadId": tid, "input": [{"type": "text", "text": text}], **kw})
        return r.get("result", {}).get("turn", {}).get("id")

    def run_until_done(label, on_request, steer=None, interrupt_after=None):
        start = time.time()
        steered = False
        turn_id = None
        while True:
            f = p.next()
            if f is None:
                notes.append("app-server exited"); return
            m = f.get("method")
            if m == "turn/started":
                turn_id = f["params"].get("turn", {}).get("id")
            if "id" in f and m:  # server request
                notes.append(f"{label} server request: {m}")
                p.send({"jsonrpc": "2.0", "id": f["id"], "result": on_request(m, f.get("params", {}))})
            if steer and not steered and m in ("item/started", "item/agentMessage/delta") and turn_id:
                steered = True
                r = p.call("turn/steer", {"threadId": tid, "expectedTurnId": turn_id,
                                          "input": [{"type": "text", "text": steer}]})
                notes.append(f"{label} steer: {json.dumps(r)[:200]}")
            if interrupt_after and turn_id and time.time() - start > interrupt_after:
                interrupt_after = None
                r = p.call("turn/interrupt", {"threadId": tid, "turnId": turn_id})
                notes.append(f"{label} interrupt: {json.dumps(r)[:200]}")
            if m == "turn/completed":
                notes.append(f"{label} completed: {json.dumps(f['params'].get('turn', {}).get('status'))}")
                return

    turn("Create a file a.txt containing hi, then say DONE1.", sandboxPolicy={"type": "workspaceWrite"})
    run_until_done("t1", lambda m, _p: {"decision": "accept"}, steer="Also say STEERSEEN at the end.")
    turn("Run the shell command `curl -s -X POST https://example.com` and report what happened.")
    run_until_done("t2", lambda m, _p: {"decision": "decline"})
    turn("Run `sleep 30 && echo slept`.")
    run_until_done("t3", lambda m, _p: {"decision": "accept"}, interrupt_after=8)
    turn("If you have any MCP tool available, call one harmless read-only MCP tool once (for example a list or "
         "search tool) and say which one. If none, say NOMCP.")
    run_until_done("t4", lambda m, _p: {"decision": "accept", "action": "accept"})
    p.close()
    after = snapshot("~/.codex/sessions/**/*.jsonl")
    notes.append(f"new codex session files: {sorted(after - before)}")
    notes.append(f"a.txt exists: {os.path.exists(os.path.join(d, 'a.txt'))}")
    print("\n".join(notes))


if __name__ == "__main__":
    os.makedirs(FIX, exist_ok=True)
    {"claude": claude, "codex": codex}[sys.argv[1]]()
