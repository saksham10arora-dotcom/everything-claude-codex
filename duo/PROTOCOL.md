# How duo talks to Claude Code and Codex

Verified 2026-11-10 with Claude Code 2.1.316 and codex-cli 0.165.0 by `duo/probe.py`.
Raw frames: `tests/fixtures/duo/claude_probe.jsonl`, `codex_probe.jsonl` (ungated run), `codex_gated.jsonl`
(the setup duo actually uses). Rerun the probe after either CLI updates.

## Claude Code

Command (cwd = work folder):

```
claude -p --input-format stream-json --output-format stream-json --verbose
  --permission-mode default --permission-prompts host --permission-prompt-tool stdio
  --no-session-persistence --settings '{"disableAllHooks": true}'
  --model <model> [--effort <level>] --append-system-prompt <brief>
```

- `--permission-prompt-tool stdio` is required. Without it, `--permission-prompts host` alone auto-denies
  (`system/permission_denied`, "you haven't granted it yet") and no request reaches us.
- First frame we send: `{"type":"control_request","request_id":"<id>","request":{"subtype":"initialize"}}`.
  Reply is a `control_response` listing commands/skills.
- User message: `{"type":"user","message":{"role":"user","content":"<text>"}}`. Sending one mid-turn works: it is
  picked up within the same run (probe: MIDSEEN appeared in the turn's final answer).
- Permission request (stdout):
  `{"type":"control_request","request_id":"<uuid>","request":{"subtype":"can_use_tool","tool_name":"Write",
  "display_name":"Write","input":{...},"description":"a.txt","permission_suggestions":[...],"tool_use_id":"..."}}`
- Our answer (stdin):
  `{"type":"control_response","response":{"subtype":"success","request_id":"<uuid>",
  "response":{"behavior":"allow","updatedInput":<input>}}}` or `{"behavior":"deny","message":"<why>"}`.
- Interrupt: `{"type":"control_request","request_id":"<id>","request":{"subtype":"interrupt"}}` → `control_response`
  with `{"still_queued": []}`, then a `user` frame "[Request interrupted by user]" and a `result` with
  `subtype: error_during_execution`.
- Turn end: `{"type":"result", "subtype":"success"|"error_during_execution", "result": "<final text>", ...}`.
- Messages: `{"type":"assistant","message":{"content":[{"type":"text"|"tool_use"|"thinking", ...}]}}`.
  Tool results come back as `type: user` with `tool_result` content.
- **Thinking is redacted**: `thinking` blocks arrive with empty text and a signature. Only `system/thinking_tokens`
  counts are visible. The screen cannot show Claude's reasoning text.
- Claude itself auto-allows read-only tools and commands (e.g. `ls`, Read) without asking us. These are all things
  the policy allows anyway. **Allow rules in the work repo's `.claude/settings*.json` would also skip us**, so duo
  warns at startup when they exist. The user's global allow list is empty (checked).
- No transcript file is written under `~/.claude/projects/` (checked before/after).
- `disableAllHooks`: no hook frames appeared in the verbose stream and `init` reports no hook output, so the user's
  hooks did not run (weak evidence; the smoke run re-checks that no phone-vault sync or notification fired). Claude Code's own built-in guard still
  blocks things like `sleep 30 && ...`; that is not a user hook.

## Codex

Command: `codex app-server -c features.codex_hooks=false -c mcp_servers.<name>.default_tools_approval_mode="prompt"`
(one `-c` per server in `~/.codex/config.toml`), with env `CODEX_HOME=<duo-only home>`.

**Duo-only Codex home** (required): a folder with symlinks to the user's `auth.json`, `config.toml`, `AGENTS.md`,
`skills`. It deliberately does not include `rules/`, `hooks.json` or `sessions/`. Why: the user's
`~/.codex/rules/default.rules` has `prefix_rule(pattern=["curl"], decision="allow")`, so in the normal home
`curl -s -X POST https://example.com` ran with **no approval request** (ungated probe, turn 2). In the duo home it
produced `item/commandExecution/requestApproval` and was declined.

JSON-RPC 2.0 over stdio, one JSON object per line.

- `initialize {"clientInfo":{"name","version"}}` → result; then notify `initialized`.
- `thread/start {"cwd","ephemeral":true,"approvalPolicy":"untrusted","sandbox":"read-only"|"workspace-write",
  "developerInstructions":<brief>,"model"?}` → `result.thread.id`. Ephemeral threads wrote **no** session files
  (checked both the normal and the duo home).
- `turn/start {"threadId","input":[{"type":"text","text"}],"sandboxPolicy"?,"effort"?}` → `result.turn.id`.
  `sandboxPolicy` example: `{"type":"workspaceWrite"}`; it applies to this and later turns.
- `turn/steer {"threadId","expectedTurnId","input":[...]}` works mid-turn (probe: STEERSEEN in the reply).
- `turn/interrupt {"threadId","turnId"}` → `{}`; `turn/completed` then has `turn.status: "interrupted"`.
- Notifications used: `turn/started` (`params.turn.id`), `item/started`, `item/completed` (`params.item`:
  `type` = `userMessage` | `agentMessage` (`text`) | `reasoning` (summary, may be empty) | `commandExecution`
  (`command`, `status`, `exitCode`, `aggregatedOutput`) | `fileChange` (`changes`) | `mcpToolCall` (`server`,
  `tool`, `status`)), `item/agentMessage/delta`, `item/reasoning/summaryTextDelta`, `turn/completed`
  (`params.turn.status`: `completed` | `interrupted` | `failed`).
- Server requests we must answer (`{"id":<their id>,"result":...}`):
  - `item/commandExecution/requestApproval` (`command`, `cwd`, `reason`) → `{"decision":"accept"|"decline"}`.
  - `item/fileChange/requestApproval` → `{"decision":"accept"|"decline"}` (shape from schema; not hit in the probe
    because Codex wrote the file through a shell command).
  - `mcpServer/elicitation/request` with `_meta.codex_approval_kind == "mcp_tool_call"`, `serverName`, the tool name
    only inside `message` (`Allow the <server> MCP server to run tool "<tool>"?`), `_meta.tool_params` →
    `{"action":"accept","content":{}}` or `{"action":"decline"}`. Declined calls end as `mcpToolCall` `failed`.
- Interrupting while a command is already approved and running does not kill that command (probe: `sleep 30`
  still completed). Duo treats interrupt as "stop after the current step".

- `item/fileChange/requestApproval` params carry only `itemId`; the paths come from the matching `item/started`
  `fileChange` item (`changes: [{path, kind: {type: add|delete|update}, diff}]`). Verified: a patch deleting a file
  produced the approval, and `decline` left the file in place (`codex_filechange.jsonl`). Under `untrusted`, even
  `cat README.md` asks; the policy allows it.
- Paths are reported as real paths (`/private/var/...` for `/var/...`); the policy resolves symlinks.
- The user's AGENTS.md "confirm before deleting" rule makes Codex ask in chat before deleting, on top of duo's card.
- ChatGPT app connectors use `-c apps._default.default_tools_approval_mode="prompt"` (key from the `AppsConfig`
  schema; Codex accepts it without an "unrecognized setting" warning).
