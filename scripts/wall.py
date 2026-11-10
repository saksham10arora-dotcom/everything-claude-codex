#!/usr/bin/env python3
"""Refresh the ECX wall in README.md: everyone who starred the repo, as linked avatars.

    python3 scripts/wall.py        (needs the GitHub CLI `gh`, signed in; GitHub only lists stargazers to signed-in users)

It rewrites only the part of README.md between <!-- wall:stars:start --> and <!-- wall:stars:end -->.
"""
import json
import os
import subprocess

REPO = "saksham10arora-dotcom/everything-claude-codex"
README = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")
START, END = "<!-- wall:stars:start -->", "<!-- wall:stars:end -->"


def stargazers():
    out = subprocess.run(["gh", "api", "--paginate", f"repos/{REPO}/stargazers?per_page=100", "-q", ".[].login"],
                         capture_output=True, text=True, check=True).stdout
    return [u for u in out.split() if not u.endswith("[bot]")]


def block(users):
    faces = "".join(f'<a href="https://github.com/{u}"><img src="https://github.com/{u}.png?size=80" width="40" height="40" '
                    f'alt="{u}" title="{u}" /></a>' for u in reversed(users))
    return f'{START}\n<p>\n{faces}\n</p>\n{END}'


def main():
    text = open(README, encoding="utf-8").read()
    if START not in text or END not in text:
        raise SystemExit("README.md has no wall markers")
    users = stargazers()
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    open(README, "w", encoding="utf-8").write(head + block(users) + tail)
    print(f"wall: {len(users)} stargazers")


if __name__ == "__main__":
    main()
