# Contributing to ECX

Thanks for helping. ECX is small and every issue names the exact files to touch, so a first PR is usually an evening's work.

## Find an issue

- **First PR here?** Pick a [`good first issue`](https://github.com/saksham10arora-dotcom/everything-claude-codex/labels/good%20first%20issue). These are kept for people who haven't had a PR merged yet.
- **Already merged one?** Pick from [`help wanted`](https://github.com/saksham10arora-dotcom/everything-claude-codex/labels/help%20wanted), so newcomers always have a way in.
- Comment "I'll take this" on the issue first, and work on one issue at a time. If a claimed issue has no PR after 7 days, it's open again.

Stuck or unsure? Ask on the issue. Questions are welcome and get answered.

## Set up

You need Python 3.9 or newer. No packages are needed to run the tests.

```bash
git clone https://github.com/<you>/everything-claude-codex
cd everything-claude-codex
python3 -m unittest discover -s tests -v
```

Want to see what the installer would do without touching your machine?

```bash
./install.sh --vault /tmp/test-vault --name Test --dry-run
```

## Where things live

| Folder | What it is |
|---|---|
| `skills/<name>/SKILL.md` | Slash commands. Plain markdown, no code needed. |
| `hooks/` | Scripts Claude Code and Codex run on events. Registered in `scripts/install.py` (`add_hooks(...)`). |
| `scripts/` | `install.py`, `uninstall.py`, `doctor.py` |
| `tests/` | `unittest` tests, run on macOS and Linux in CI |

## Rules for a PR

- **One change per PR.** Link the issue with `Closes #N`.
- **Add a test** for anything you change in `hooks/` or `scripts/`.
- **Hooks must never crash or block by accident:** catch errors and exit 0.
- **Run the tests before you push.** CI runs the same command on Python 3.9 and 3.12.
- **You should be able to explain every line.** AI help is fine, but a PR you can't answer questions about will be closed.

## Add a skill

1. Create `skills/<name>/SKILL.md`. Copy the frontmatter from [`skills/boot/SKILL.md`](skills/boot/SKILL.md): a `name`, and a `description` listing the phrases that trigger it.
2. Write the steps the agent should follow and the exact output format.
3. Re-run `./install.sh`. It links every folder in `skills/`, so your skill shows up in Claude Code and Codex right away.

Got a skill or hook from your own setup that others would want? Share it in [Discussions](https://github.com/saksham10arora-dotcom/everything-claude-codex/discussions).
