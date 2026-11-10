"""Stands in for `claude -p` stream-json: one turn with a message, a permission request, then a result."""
import json
import os
import sys

out = open(os.environ["FAKE_OUT"], "a")
out.write(json.dumps({"argv": sys.argv[1:]}) + "\n"); out.flush()


def emit(o):
    sys.stdout.write(json.dumps(o) + "\n"); sys.stdout.flush()


for line in sys.stdin:
    f = json.loads(line)
    out.write(json.dumps(f) + "\n"); out.flush()
    if f.get("type") == "control_request" and f["request"]["subtype"] == "initialize":
        emit({"type": "control_response", "response": {"subtype": "success", "request_id": f["request_id"], "response": {}}})
    elif f.get("type") == "user":
        emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "I will write a.txt"}]}})
        emit({"type": "control_request", "request_id": "perm-1", "request": {
            "subtype": "can_use_tool", "tool_name": "Write", "input": {"file_path": "a.txt", "content": "hi"}}})
    elif f.get("type") == "control_response":
        emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Write",
                                                            "input": {"file_path": "a.txt"}}]}})
        emit({"type": "result", "subtype": "success", "result": "done"})
