"""Append-only event log for one duo run: the single source of truth for the screen and the audit."""
import json
import os
import queue
import threading
import time

AGENTS = {"claude", "codex", "user", "duo"}
KINDS = {"message", "reasoning", "tool", "tool_result", "file_change", "card_open", "card_resolved", "blocked",
         "status", "signal", "error", "report", "usage", "turn"}


class EventLog:
    def __init__(self, path):
        self.path = path
        self._lock = threading.Lock()
        self._events = EventLog.load(path) if os.path.exists(path) else []
        self._subs = []

    def add(self, agent, kind, **data):
        if agent not in AGENTS or kind not in KINDS:
            raise ValueError(f"unknown agent/kind: {agent}/{kind}")
        with self._lock:
            e = {"seq": len(self._events) + 1, "ts": time.time(), "agent": agent, "kind": kind, **data}
            with open(self.path, "a") as f:
                f.write(json.dumps(e) + "\n")
                f.flush()
                os.fsync(f.fileno())
            self._events.append(e)
            subs = list(self._subs)
        for q in subs:
            q.put(e)
        return e

    def since(self, seq):
        with self._lock:
            return [e for e in self._events if e["seq"] > seq]

    def all(self):
        return self.since(0)

    def subscribe(self):
        q = queue.Queue()
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    @staticmethod
    def load(path):
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]
