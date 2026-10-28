#!/bin/bash
# PostToolUse (Write|Edit): flag the classic AI-writing tell (the em dash) in
# anything you'll publish. Only checks folders listed in ECX_PUBLISH_DIRS
# (default: content, personal). Warns, never blocks.
f=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path") or d.get("tool_response",{}).get("filePath") or "")' 2>/dev/null)
[ -f "$f" ] || exit 0
for d in ${ECX_PUBLISH_DIRS:-content personal}; do
  case "$f" in
    */"$d"/*)
      if grep -q "—" "$f"; then
        printf '{"systemMessage":"AI tell: em dash found in %s. Rewrite those sentences before publishing."}\n' "$(basename "$f")"
      fi
      exit 0;;
  esac
done
exit 0
