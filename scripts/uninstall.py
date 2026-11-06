#!/usr/bin/env python3
"""ECX uninstaller. Restores every settings file install.py backed up (*.ecx-bak)
and removes the skill links that point into this repo. Anything else is left alone.

    python3 scripts/uninstall.py --vault ~/vault
    ./install.sh --uninstall --vault ~/vault
"""
import argparse
import os

ECX = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
SKILL_DIRS = [os.path.join(HOME, ".claude", "skills"), os.path.join(HOME, ".agents", "skills")]


def say(sym, msg):
    print(f"  {sym} {msg}")


def find(roots, suffix):
    """Find files ending in suffix at each root and one folder level below it (dot-folders included)."""
    found = {}   # keyed by normalized path: the vault can sit inside HOME, so roots overlap
    for root in roots:
        if not os.path.isdir(root):
            continue
        dirs = [root] + [os.path.join(root, d) for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))]
        for d in dirs:
            for n in os.listdir(d):
                if n.endswith(suffix):
                    p = os.path.join(d, n)
                    found.setdefault(os.path.normcase(os.path.abspath(p)), p)
    return sorted(found.values())


def restore(backup):
    """Put back the copy install.py saved before it first changed this file."""
    path = backup[:-len(".ecx-bak")]
    os.replace(backup, path)
    say("<", f"restored {path.replace(HOME, '~')}")


def remove_created(marker):
    """install.py made this file from nothing (marker *.ecx-new), so remove it."""
    path = marker[:-len(".ecx-new")]
    if os.path.exists(path):
        os.remove(path)
        say("-", f"removed {path.replace(HOME, '~')} (created by ECX)")
    os.remove(marker)


def points_into_ecx(link):
    if not os.path.islink(link):
        return False
    raw = os.readlink(link)
    if raw.startswith("\\\\?\\"):   # Windows reports links with a \\?\ prefix
        raw = raw[4:]
    target = os.path.normcase(os.path.abspath(raw))
    skills = os.path.normcase(os.path.abspath(os.path.join(ECX, "skills")))
    return os.path.dirname(target) == skills


def remove_link(link):
    if os.name == "nt" and os.path.isdir(link):
        os.rmdir(link)   # directory symlinks on Windows are removed with rmdir
    else:
        os.unlink(link)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=os.path.join(HOME, "vault"))
    a = ap.parse_args()
    vault = os.path.realpath(os.path.expanduser(a.vault))

    print(f"\nECX: uninstalling\n  vault: {vault}\n")

    # 1. Settings files install.py changed: restore the backups, remove the ones it created
    print("Settings")
    roots = [HOME, vault]
    backups = find(roots, ".ecx-bak")
    created = find(roots, ".ecx-new")
    for b in backups:
        restore(b)
    for m in created:
        remove_created(m)
    if not backups and not created:
        say("i", "no .ecx-bak files found, nothing to restore")

    # 2. Skill links that point into this repo
    print("Skills")
    for target in SKILL_DIRS:
        if not os.path.isdir(target):
            continue
        removed = 0
        for name in sorted(os.listdir(target)):
            link = os.path.join(target, name)
            if points_into_ecx(link):
                remove_link(link)
                removed += 1
        say("-", f"{removed} skill links removed from {target.replace(HOME, '~')}")

    print("\nDone. Your own files and skills were not touched.\n")


if __name__ == "__main__":
    main()
