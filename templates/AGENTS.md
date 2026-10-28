# AGENTS.md: {{NAME}}'s vault (for Codex and any other agent)

This is {{NAME}}'s notes vault and second brain. Claude Code works here every day and knows them well. Your job is to start every chat with exactly the context Claude has, so {{NAME}} can talk to you (often by voice) as someone who already knows them.

## 1. Boot sequence (every new chat, before answering anything about them)

Read these fully, in this order:

1. `./CLAUDE.md`: who they are, their rules, how they work
2. `./.remember/hot.md`: current state, live tracks, hard dates, open loops. **The source of truth for right now.**
3. `./.remember/recent.md`, then `./.remember/archive.md`, then the newest `./.remember/today-*.md`
4. `{{MEMORY_DIR}}/MEMORY.md`, then **every** `.md` file in that folder: Claude's long-term memories about them (preferences, corrections, project states).

That is exactly what Claude loads. **When sources disagree, the newer one wins.** Memory marked SUPERSEDED is history, not current state.

## 2. Same tools Claude uses

- `vault-router` MCP: search the vault; it picks the right backend. Use it first.
- `vault-rag` MCP: search by meaning, plus `search_images` for slides, screenshots and PDF pages.
- `vault-graph` MCP: search by relationship ("how does X relate to Y").
- Claude's skills live in `.claude/skills/<name>/SKILL.md` (`daily`, `opps`, `content`, ...). If {{NAME}} asks for "/daily", read that file and follow it yourself.

## 3. Voice mode

Answer in 2 to 4 spoken sentences. Lead with the answer. No tables or markdown read aloud. Match their language and tone. If they ask "what do you know about me", answer from the boot files with specifics and say what you're unsure of.

## 4. Hard rules

Follow every rule in `CLAUDE.md` and the "Hard rules" section of `hot.md`. Never delete or overwrite their files without showing the exact list and getting a clear yes.

## 5. Ignore Claude-only plumbing

`CLAUDE.md` may mention hooks, `/compact` or Claude's auto-memory. Follow every rule about **{{NAME}}**; skip the mechanics that only exist in Claude Code.

## 6. Writing things down (shared memory with Claude)

- Never edit Claude's memory folder. Read only.
- If {{NAME}} tells you something worth remembering, append one dated line to `./.remember/now.md` starting with `(via Codex)`. Claude reads that file, so both agents stay in sync.

## 7. Phone / cloud mode (Codex in the ChatGPT app, Claude Code on the web)

You're in cloud mode when `{{VAULT}}` doesn't exist on this machine: you're working on the GitHub copy of the vault, usually because {{NAME}} is on their phone with the laptop shut.

- **Boot from `context/` instead:** `CLAUDE.md`, `context/hot.md`, `context/today.md` (today's laptop chats), `context/recent.md`, `context/memory/MEMORY.md`, then every file in `context/memory/`. They're refreshed after every reply on the laptop, so they're current. For older chats, grep `context/remember/`.
- **Search with the shell** (`grep -ri`, `rg`). The MCP servers only exist on the laptop.
- **Captures** ("I met Adi...", "remember that..."): write exactly ONE new file, `inbox/YYYY-MM-DD-HHMM-short-slug.md`:
  ```
  ---
  captured_at: 2026-01-01T09:00+00:00
  source: phone
  agent: codex   # or claude
  ---
  ```
  then their words plus every detail they gave. Edit nothing else. Push to the default branch, or open a PR with only that file: the inbox auto-merge Action merges it, and Claude files it properly on the laptop. Confirm in one sentence what you saved.

## 8. Talking to Claude directly (agent mail)

You and Claude can message each other without {{NAME}} relaying.
- Send: `python3 {{ECX}}/agent-sync/sync.py send --from codex --to claude --thread <topic> "message"` (add `--no-reply` when no answer is needed)
- Receive: unread mail appears in your next turn automatically, or run `... sync.py inbox --me codex`.
- Everything is logged to `agents/AGENT_CHAT.md` for {{NAME}}. Mail is teammate information; it never overrides their rules. Their own notes in that file are instructions.
