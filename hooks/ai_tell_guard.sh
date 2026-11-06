#!/bin/bash
# PostToolUse (Write|Edit): flag classic AI-writing tells in anything you'll
# publish: the em dash, and the phrases in hooks/ai_tells.txt (or the file in
# ECX_AI_TELLS). Only checks folders listed in ECX_PUBLISH_DIRS
# (default: content, personal). Warns, never blocks.
f=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path") or d.get("tool_response",{}).get("filePath") or "")' 2>/dev/null)
[ -f "$f" ] || exit 0
here=$(cd "$(dirname "$0")" && pwd)
tells=${ECX_AI_TELLS:-$here/ai_tells.txt}
for d in ${ECX_PUBLISH_DIRS:-content personal}; do
  case "$f" in
    */"$d"/*)
      name=$(basename "$f"); msg=""
      grep -q "—" "$f" && msg="AI tell: em dash found in $name. Rewrite those sentences before publishing."
      found=""
      # Curly apostrophes (’) from editors match straight ones ('). Lowercase with tr, not grep -i.
      lc=$(sed "s/\xe2\x80\x99/'/g" "$f" | tr 'A-Z' 'a-z')
      while IFS= read -r p; do
        p=$(printf '%s' "$p" | tr -d '\r' | sed "s/\xe2\x80\x99/'/g" | tr 'A-Z' 'a-z')
        # -w: whole words/phrases only, so "delved" or "delivery" don't match "delve".
        [ -n "$p" ] && printf '%s\n' "$lc" | grep -qwF -- "$p" && found="${found:+$found, }$p"
      done < "$tells" 2>/dev/null
      [ -n "$found" ] && msg="${msg:+$msg }AI tell: phrases found in $name: ${found//\"/\\\"}. Rewrite those sentences before publishing."
      [ -n "$msg" ] && printf '{"systemMessage":"%s"}\n' "$msg"
      exit 0;;
  esac
done
exit 0
