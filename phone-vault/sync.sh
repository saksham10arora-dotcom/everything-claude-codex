#!/bin/bash
# vault-sync: keep the GitHub copy of the vault fresh so phone agents can use it.
# Mirrors "who you are" (hot.md, session summaries, Claude's memory files) into
# context/, commits changed/new .md notes, pulls phone captures, pushes.
# Triggered after every agent reply by the Stop hook. Never force-pushes.
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

VAULT="${ECX_VAULT:-$HOME/vault}"
# Claude's auto-memory for this project lives under ~/.claude/projects/<path with / -> ->/memory
MEM="$HOME/.claude/projects/$(cd "$VAULT" 2>/dev/null && pwd -P | sed 's/[^A-Za-z0-9]/-/g')/memory"
STATE="$HOME/.vault-sync"
LOCK="$STATE/lock"; PENDING="$STATE/pending"; LOG="$STATE/sync.log"
mkdir -p "$STATE"
log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

# One runner at a time. A second trigger just asks the runner for one more pass.
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +10 2>/dev/null)" ]; then
    rm -rf "$LOCK"; mkdir "$LOCK" 2>/dev/null || exit 0      # stale lock from a crash
  else
    touch "$PENDING"; exit 0
  fi
fi
trap 'rm -rf "$LOCK"' EXIT
cd "$VAULT" || { log "vault missing"; exit 0; }

run_once() {
  if [ "$(git rev-parse --abbrev-ref HEAD 2>/dev/null)" != "master" ]; then log "skip: not on master"; return; fi
  if [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ] || [ -f .git/MERGE_HEAD ]; then log "skip: git busy"; return; fi
  # another git command (a commit from a chat) holds the index: wait up to 10 s instead of failing
  for _ in 1 2 3 4 5 6 7 8 9 10; do [ -f .git/index.lock ] || break; sleep 1; done
  if [ -f .git/index.lock ]; then touch "$PENDING"; log "skip: index locked, retrying next run"; return; fi

  # 1. mirror context (one-way, Mac -> repo)
  mkdir -p context/memory
  [ -f .remember/hot.md ] && cp .remember/hot.md context/hot.md
  [ -f .remember/recent.md ] && cp .remember/recent.md context/recent.md
  # today's Mac sessions (recent.md only gets them after the daily rotation)
  t=$(ls -t .remember/today-*.md 2>/dev/null | grep -v '\.done\.md$' | head -1)
  { [ -n "$t" ] && { printf '# Mac sessions, %s\n\n' "$(basename "$t" .md | sed 's/^today-//')"; cat "$t"; }
    [ -s .remember/now.md ] && cat .remember/now.md; } > context/today.md   # now.md = newest entries, not yet folded into today
  # daily session summaries since April + archive (summaries only, never raw chats)
  rsync -a --delete --include='*.md' --exclude='*' .remember/ context/remember/
  [ -d "$MEM" ] && rsync -a --delete --include='*/' --include='*.md' --exclude='*' "$MEM/" context/memory/

  # 2. commit notes only: every new/changed/deleted .md, plus context/
  git add -A -- context ':(glob)**/*.md' ':(exclude,glob)**/.margin-history/**' 2>>"$LOG"
  if ! git diff --cached --quiet; then
    n=$(git diff --cached --name-only | wc -l | tr -d ' ')
    git commit -q -m "sync: $n note(s) $(date '+%F %H:%M')" >>"$LOG" 2>&1 || { log "commit failed"; return; }
  fi

  # 3. take phone captures first, then push. Never force.
  if ! git pull -q --rebase --autostash origin master >>"$LOG" 2>&1; then
    git rebase --abort >/dev/null 2>&1
    log "CONFLICT: pull failed, nothing pushed"
    osascript -e 'display notification "Vault sync hit a conflict. Ask Claude to look." with title "vault-sync"' >/dev/null 2>&1
    return
  fi
  if [ "$(git rev-list --count origin/master..master 2>/dev/null)" != "0" ]; then
    if git push -q origin master >>"$LOG" 2>&1; then log "pushed"; else log "push failed (offline?)"; fi
  fi
}

for _ in 1 2 3; do
  rm -f "$PENDING"
  run_once
  [ -f "$PENDING" ] || break
done
