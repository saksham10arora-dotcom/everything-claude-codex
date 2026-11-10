"""Stands in for `codex app-server`: one turn with a message and a delete-file approval request."""
import json
import os
import sys

out = open(os.environ["FAKE_OUT"], "a")
out.write(json.dumps({"argv": sys.argv[1:], "codex_home": os.environ.get("CODEX_HOME")}) + "\n"); out.flush()
cwd = os.getcwd()


def emit(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()


def note(method, **p):
    emit({"jsonrpc": "2.0", "method": method, "params": {"threadId": "th1", **p}})


for line in sys.stdin:
    f = json.loads(line)
    out.write(json.dumps(f) + "\n"); out.flush()
    m = f.get("method")
    if m == "initialize":
        emit({"jsonrpc": "2.0", "id": f["id"], "result": {}})
    elif m == "mcpServerStatus/list":
        names = [n for n in os.environ.get("FAKE_MCP", "").split(",") if n]
        emit({"jsonrpc": "2.0", "id": f["id"], "result": {"data": [{"name": n} for n in names], "nextCursor": None}})
    elif m == "turn/start" and os.environ.get("FAKE_FAIL_TURN"):
        emit({"jsonrpc": "2.0", "id": f["id"], "error": {"code": -1, "message": "model unavailable"}})
    elif m == "thread/start":
        emit({"jsonrpc": "2.0", "id": f["id"], "result": {"thread": {"id": "th1"}}})
    elif m == "turn/start":
        emit({"jsonrpc": "2.0", "id": f["id"], "result": {"turn": {"id": "tu1"}}})
        note("turn/started", turn={"id": "tu1"})
        note("item/completed", item={"type": "agentMessage", "id": "m1", "text": "hello from codex"})
        note("item/started", item={"type": "fileChange", "id": "fc1", "status": "inProgress",
                                   "changes": [{"path": os.path.join(cwd, "old.py"), "kind": {"type": "delete"}, "diff": ""}]})
        emit({"jsonrpc": "2.0", "id": 100, "method": "item/fileChange/requestApproval",
              "params": {"threadId": "th1", "turnId": "tu1", "itemId": "fc1", "startedAtMs": 1}})
    elif m == "turn/steer":
        emit({"jsonrpc": "2.0", "id": f["id"], "result": {"turnId": "tu1"}})
    elif m == "turn/interrupt":
        emit({"jsonrpc": "2.0", "id": f["id"], "result": {}})
    elif f.get("id") == 100:
        status = "completed" if f["result"]["decision"] == "accept" else "declined"
        note("item/completed", item={"type": "fileChange", "id": "fc1", "status": status,
                                     "changes": [{"path": os.path.join(cwd, "old.py"), "kind": {"type": "delete"}, "diff": ""}]})
        note("turn/completed", turn={"id": "tu1", "status": "completed"})
