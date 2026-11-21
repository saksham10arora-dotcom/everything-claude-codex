#!/bin/bash
# ECX one-line install:  ./install.sh            (asks three questions)
#                        ./install.sh --vault ~/notes --name Ada --with-search --with-cron --with-phone
#                        ./install.sh --uninstall --vault ~/notes   (restores *.ecx-bak files, removes skill links)
set -e
cd "$(dirname "$0")"
PY=$(command -v python3) || { echo "ECX needs python3 (3.9+)"; exit 1; }
if [[ "$1" == "--uninstall" ]]; then shift; exec "$PY" scripts/uninstall.py "$@"; fi
if [[ "$*" != *--vault* ]]; then
  read -r -p "Where should your vault (notes folder) live? [~/vault] " V; V=${V:-~/vault}
  read -r -p "Your first name (agents use it): " N; N=${N:-me}
  read -r -p "Add this install to the public count? One request to GitHub, nothing about you is sent. [y/N] " C
  set -- --vault "${V/#\~/$HOME}" --name "$N" "$@"
  if [[ "$C" =~ ^[Yy] ]]; then set -- "$@" --count-install; fi
fi
exec "$PY" scripts/install.py "$@"
