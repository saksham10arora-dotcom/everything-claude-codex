"""The live screen's local server: the page, an SSE stream of the event log, and the user's actions."""
import argparse
import json
import os
import queue
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html")
ACTIONS = {"pause", "resume", "stop"}


def start_server(log, orch, run_dir, port=0):
    token = secrets.token_urlsafe(16)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _ok(self, body, ctype="text/plain; charset=utf-8", code=200):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _deny(self):
            self._ok("forbidden", code=403)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if not secrets.compare_digest(q.get("t", [""])[0], token):
                return self._deny()
            if u.path == "/":
                return self._ok(open(WEB, "rb").read(), "text/html; charset=utf-8")
            if u.path == "/plan":
                p = os.path.join(run_dir, "plan.md")
                return self._ok(open(p).read() if os.path.exists(p) else "")
            if u.path == "/events":
                return self._events(int(q.get("since", ["0"])[0] or 0))
            self._ok("not found", code=404)

        def _events(self, since):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            sub = log.subscribe()
            try:
                last = since
                for e in log.since(since):
                    self.wfile.write(f"data: {json.dumps(e)}\n\n".encode())
                    last = e["seq"]
                self.wfile.flush()
                while True:
                    try:
                        e = sub.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        continue
                    if e["seq"] <= last:
                        continue
                    last = e["seq"]
                    self.wfile.write(f"data: {json.dumps(e)}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                log.unsubscribe(sub)

        def do_POST(self):
            if not secrets.compare_digest(self.headers.get("X-Duo-Token", ""), token):
                return self._deny()
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            except ValueError:
                return self._ok("bad json", code=400)
            path = urllib.parse.urlparse(self.path).path
            if path == "/say" and str(body.get("text", "")).strip():
                orch.say(str(body["text"]).strip())
            elif path == "/card" and body.get("id") and body.get("decision") in ("approve", "deny"):
                orch.resolve_card(str(body["id"]), body["decision"], str(body.get("note", "")))
            elif path == "/control" and body.get("action") in ACTIONS:
                orch.control(body["action"])
            else:
                return self._ok("bad request", code=400)
            self._ok("ok")

    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/?t={token}"

    def stop():
        httpd.shutdown()
        httpd.server_close()
    return url, stop


class ReplayOrch:
    """For looking at the screen without running agents: user actions just land in the log."""

    def __init__(self, log):
        self.log = log

    def say(self, text):
        self.log.add("user", "message", text=text, to=["claude", "codex"])

    def resolve_card(self, cid, decision, note=""):
        self.log.add("user", "card_resolved", id=cid, decision=decision, note=note)

    def control(self, action):
        self.log.add("duo", "status", status={"pause": "paused", "resume": "running", "stop": "stopped"}[action],
                     reason=f"{action} (replay)")


if __name__ == "__main__":
    from duo.events import EventLog
    ap = argparse.ArgumentParser(description="Serve the duo screen over a recorded event log.")
    ap.add_argument("--replay", required=True)
    ap.add_argument("--port", type=int, default=0)
    a = ap.parse_args()
    import shutil, tempfile
    rd = tempfile.mkdtemp(prefix="duo-replay-")
    events = EventLog.load(a.replay)
    log = EventLog(os.path.join(rd, "events.jsonl"))
    plan = os.path.join(os.path.dirname(a.replay), "sample_plan.md")
    if os.path.exists(plan):
        shutil.copy(plan, os.path.join(rd, "plan.md"))
    url, _ = start_server(log, ReplayOrch(log), rd, a.port)
    print(url, flush=True)
    for e in events:  # replay with the original data, fresh seq numbers
        log.add(e["agent"], e["kind"], **{k: v for k, v in e.items() if k not in ("seq", "ts", "agent", "kind")})
        time.sleep(0.05)
    threading.Event().wait()
