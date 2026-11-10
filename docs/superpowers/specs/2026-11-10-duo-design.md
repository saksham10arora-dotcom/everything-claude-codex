# ecx duo: Claude and Codex working together, live

Date: 2026-11-10. Status: approved in chat by Saksham, pending build.

## Intent

agent-sync made Claude and Codex share memory: each one knows what you said to the other. `duo` is the next step.
You give one goal, and the two agents work on it **together and on their own**: they plan, argue, agree, split the work
and build, while you watch the whole thing live in one screen and can step in at any moment.

The point is that two different models working together should be smarter than either alone. That only happens if
they really challenge each other. Polite agreement is the failure mode.

Both agents serve one boss, the user. Every decision is judged by "what is best for the user", not "what keeps the peace".

## Goals

- One command starts it: `ecx duo "<goal>"` (run inside the folder they should work in).
- Full autonomy between start and stop. **No roles.** No lead, no builder, no reviewer, unless the agents themselves
  decide to split work that way. They choose what to do, who does what, when to argue and when it is finished.
- One live screen (a local web page) shows:
  - one chat with both agents' messages, interleaved in real time;
  - every command they run and file they change, collapsed by default, expandable;
  - the current shared plan (done / in progress / next);
  - approval cards and the final report.
- The user can talk into it at any time:
  - `@claude ...` or `@codex ...` goes to that one agent;
  - a message without a mention goes to both.
  - The agent should see it as soon as possible, mid-turn if the tool allows it, not only after it finishes.
- The user holds the switch: pause, resume, stop, any time.
- Real disagreement is expected and shown. The screen flags when they have gone in circles on the same point for a long
  time, so the user can step in. It does not stop them.

## The flow

1. **Kickoff.** User runs `ecx duo "<goal>"`. The screen opens.
2. **Plan together.** Both agents read the goal and the folder, then argue out one joint plan. Where they still disagree,
   the plan says so plainly with both positions.
3. **Plan approval.** The plan appears as a card: Approve, or Send back with a note. Nothing gets built before approval.
   They may write notes or scratch files while planning, but they do not change the user's project yet.
4. **Build.** Autonomous. They split work however they like, change their minds, argue and agree again. If they decide
   the approved plan needs a big change, they show the change as a new plan card for approval.
5. **Ask before anything destructive or outward-facing.** Each such action pauses that agent and shows an approval card
   (what, why, which agent): Approve / Deny / Deny with a note. Covered:
   - deleting or overwriting files outside the work they created in this run, `rm -rf`-style commands, `git reset --hard`,
     force pushes, history rewrites;
   - `git push`, publishing, deploys, opening PRs or issues;
   - sending any message, email or post;
   - anything that spends money or calls a paid API the user has not already set up for this project;
   - installing global packages or changing system or user config outside the work folder.
   Normal work (reading, editing files in the work folder, running tests, local commits on a branch) needs no approval.
6. **Done by consensus.** When both agents agree the goal is finished, they write one report together:
   - what was built, with commits and files;
   - where they disagreed and how it was settled (or that it wasn't);
   - what is still open;
   - what the user should do next.
   The report shows in the screen and is saved to a file in the run folder.
7. **Stop.** The user can stop at any time; both agents are interrupted, and a short partial report is still written from
   what happened so far.

## How they behave (their starting brief)

Both agents get the same brief, written into the run, covering:

- You are working with another AI (named) on this goal for the user. You both work for the user.
- Challenge each other. If you think the other is wrong, say so and argue why. Never agree just to agree.
- Agree only when you have been genuinely convinced, or when evidence settles it (a test passes, a benchmark is better,
  the docs say so).
- No roles are assigned. Decide between you how to split the work. Say clearly what you are taking so you don't both
  edit the same thing.
- The user may interrupt with a message. A message addressed to you is an instruction from the boss; a message to both
  is for both.
- The approval rules above.
- How to signal "I think we're done" and how consensus on done is reached (both must say it).

Plus, for each agent: the user's normal setup still applies (their CLAUDE.md / AGENTS.md, agent-sync memory).

## Constraints

- **Runs both agents itself, headless, outside the desktop apps.** The user's normal Claude and Codex app histories must
  stay clean: duo sessions are kept apart (for example, a dedicated Codex home or profile, and Claude sessions tagged or
  stored per run), and must never appear as stray chats in the user's Codex app.
- Uses the user's existing logins and subscriptions. No new API keys required.
- Uses only official interfaces:
  - Claude: Claude Code in print mode with streaming JSON input and output (a long-lived session that accepts new user
    messages), with permission requests routed to the host program so they become approval cards.
  - Codex: `codex app-server` (JSON-RPC over stdio): `thread/start`, `turn/start`, `turn/steer` for mid-turn messages,
    `turn/interrupt`, and its approval requests (command execution, file change, permissions) become approval cards.
  - Versions on the dev machine: Claude Code 2.1.316, codex-cli 0.165.0. The Codex app-server protocol is marked
    experimental; pin to what is verified and fail with a clear message if it changes.
- agent-sync stays as it is. The send/inbox mail feature is paused, not deleted, and duo must not depend on it.
- Protected paths (for example `~/Downloads/yep/` for this user) are never touched; ECX's existing danger guard stays on.
- A hidden backstop cap on wall-clock time and turns (generous, configurable), in case the user walks away. When it hits,
  the run pauses and pings rather than silently ending.
- Local only. The web page binds to localhost. Nothing leaves the machine except the agents' own normal model traffic.
- Ships inside ECX: Python like the rest of the repo, tests in `tests/`, mentioned in the README.

## Non-goals

- Showing the models' raw hidden thinking. Neither tool exposes all of it. The screen shows what they write and do,
  plus Codex's reasoning summaries and Claude's visible thinking if the stream includes them.
- More than two agents, or other models, in v1.
- Remote access or phone view in v1 (a Discord ping at the end is a nice-to-have, below).
- Replacing the desktop apps for normal work.

## Anti-goals (would be a failure even if it technically works)

- The agents fold to each other and the chat is two models saying "great idea".
- A forced turn-taking script that makes it feel like a scripted demo instead of two agents working.
- Stray duo chats showing up in the user's normal Codex or Claude history.
- Anything destructive or public happening without a card the user approved.
- A run that keeps burning quota all night with nobody watching and no ping.

## Decided by the user

- Kickoff required; the user is the start and stop switch.
- No roles; the agents decide everything between start and stop.
- Plan approval before building; approval before destructive or outward actions.
- @mentions to talk to one agent, plain message to both.
- They report when they reach consensus that it is done.
- Disagreement is wanted; no polite negotiation.

## My calls (Claude's, flagged for the user to check)

- It lives in ECX as `ecx duo`, a new top-level folder `duo/`.
- Both agents run at the same time, each seeing the other's new messages as they happen (fed into its session), rather
  than strict alternating turns. The builder decides how messages are batched so neither agent is flooded.
- The "going in circles" flag and the hidden backstop cap.
- The web page is the window; it can be a single static page served by the Python process, no build step.
- Each run gets a folder (for example `.duo/<timestamp>/`) with the full event log, plan, report and approvals, so a run
  can be reviewed afterwards.
- Optional: Discord ping when the report is ready or an approval is waiting, if the user has a Discord setup.

## Settled after the builder check (Claude's calls)

- **Isolation without losing context.** Duo agents get the same context about the user that a normal session gets:
  logins, instruction files (CLAUDE.md / AGENTS.md, global and project), the auto-memory for the work folder, and the
  context files the user's startup hooks normally inject (for this user: `.remember/hot.md`, `.remember/recent.md`, the
  memory index). Duo feeds those in itself at start, so it gets the context without running the hooks.
  Agent-sync is **one-way in**: at start each duo agent gets a catch-up of the user's recent normal Claude and Codex
  sessions, but duo chatter never flows back into normal sessions.
  They do NOT run the user's hooks (no tests_before_done, notify, phone-vault sync, agent-sync inject); duo has its own:
  the danger guard plus duo's approval and message feed. Duo transcripts live in a duo-only location. Normal sessions
  learn about a run only through its saved report.
- **Tools: all on (user's decision).** Every MCP server and connector the user has stays available, including ones that
  send, publish or browse. Any use of a send / publish / post / spend / external-write tool, and any shell command that
  sends data out (`curl -X POST`, `gh`, `npm publish`, `vercel`, and similar), produces an approval card.
- **Audit log, written by duo, not by the agents (user's requirement).** The report has two parts:
  1. the agents' own summary;
  2. an **action log generated by duo from the raw event stream**, which the agents cannot edit. It lists every tool
     call and command, which agent made it, every approval card with the user's answer, every outward action
     (network, MCP send/publish, git push), every file deleted or replaced, and anything the danger guard blocked.
     Suspicious items are flagged at the top: denied cards, guard blocks, network calls, and anything touching files
     outside the work folder.
  The raw event log is saved next to it, so the user can hand the run folder to a normal session and ask "did anything
  malicious happen?"
- **Defaults (Claude's call, overridable per run):** strong but not top-tier models (Sonnet for Claude, Codex's default
  model), normal effort; `--best` switches both to their top models. Backstop: 2 hours, then pause and ping.
- **Editing existing files is normal work.** A card is needed only to delete an existing file, replace one wholesale,
  or run the destructive git commands listed. Everything is on a branch, so normal edits are reversible.
- **Git.** Each run creates its own branch (`duo/<timestamp>-<slug>`) in the work folder; both agents share one working
  tree and commit only the files they changed (`git add <paths>`, never `git add -A`). If the folder is not a git repo,
  duo stops and offers to `git init` it. The vault is excluded in v1 (its rule is commit-to-master).
- **Resume.** v1 is review-only after a stop or crash: the run folder keeps everything. A backstop pause keeps the
  process alive and waiting. Resume-later is v2; session and thread IDs are still saved so v2 can add it.

## Left to the builder

- Process supervision, message batching, the event log format, how "same point for too long" is detected.
- How each agent's edits are kept from colliding beyond the brief (for example, each declares what it is taking).
- Exact UI layout and styling, within the description above.
- How the approval rules are enforced per tool (hooks, permission callbacks, app-server approval policy), as long as
  every listed action reliably produces a card.
- Test strategy (fake agents for unit tests, one live smoke run).
