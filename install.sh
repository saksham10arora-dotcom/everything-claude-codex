#!/bin/bash
# ECX one-line install:  ./install.sh            (asks two questions)
#                        ./install.sh --vault ~/notes --name Ada --with-search --with-cron --with-phone
set -e
cd "$(dirname "$0")"
PY=$(command -v python3) || { echo "ECX needs python3 (3.9+)"; exit 1; }
if [[ "$*" != *--vault* ]]; then
  read -r -p "Where should your vault (notes folder) live? [~/vault] " V; V=${V:-~/vault}
  read -r -p "Your first name (agents use it): " N; N=${N:-me}
  set -- --vault "${V/#\~/$HOME}" --name "$N" "$@"
fi
exec "$PY" scripts/install.py "$@"
