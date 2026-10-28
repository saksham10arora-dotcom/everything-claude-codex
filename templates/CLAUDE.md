# CLAUDE.md: {{NAME}}'s second brain

## Who I am
<!-- Two or three lines: what you do, what you're aiming for, what you're great at. Claude reads this every session. -->

## Context loading (every session, including after /compact)
- `.remember/hot.md` is the source of truth for right now: deadlines, live projects, hard rules. It is injected at session start by the `session_context` hook.
- Starting the day: `/daily`. End of session: `/tldr`.
- Running in the cloud (Claude app / Claude Code on the web, laptop off)? Follow `AGENTS.md` section 7: boot from `context/`, save anything new as one note in `inbox/`.

## Vault structure
```
inbox/      drop zone: everything new lands here first, sorted later
daily/      daily notes (YYYY-MM-DD.md)
projects/   builds and their status
personal/   people, opportunities, applications, resume, trackers
research/   deep dives and playbooks
wiki/       compiled knowledge base (/wiki)
content/    drafts, queue, published log
archive/    finished work: never deleted, just moved
context/    auto-generated mirror for phone agents (do not edit)
```

## How I work
- Capture first, organize later (inbox/).
- Content must sound like me: Claude drafts, I edit.
- Ask before changing my resume, sending anything, or deleting anything.

## Talking to Codex (agent mail)
- Send: `python3 {{ECX}}/agent-sync/sync.py send --from claude --to codex --thread <topic> "message"`
- Unread mail is injected automatically. Readable log: `agents/AGENT_CHAT.md`.
