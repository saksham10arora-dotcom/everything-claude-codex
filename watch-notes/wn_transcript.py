#!/usr/bin/env python3
"""
wn_transcript.py: turn a yt-dlp .vtt caption file into a clean, timestamped
transcript. Handles YouTube auto-captions, which roll the same phrase across
several cues; word-level overlap dedup removes the triple-repetition.
"""
from __future__ import annotations
import glob, os, re

_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.\d{3} -->")


def _fmt(sec: int) -> str:
    return f"{sec // 60:02d}:{sec % 60:02d}"


def parse_vtt(vtt_path: str, chunk_seconds: int = 30) -> str:
    """Return a clean transcript with a [MM:SS] marker every ~chunk_seconds."""
    raw = open(vtt_path, encoding="utf-8").read().splitlines()
    cues = []  # (start_sec, text)
    for idx, ln in enumerate(raw):
        m = _TS.match(ln.strip())
        if not m:
            continue
        start = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        parts = []
        j = idx + 1
        while j < len(raw) and raw[j].strip():
            t = re.sub(r"<[^>]+>", "", raw[j]).strip()
            if t and not _TS.search(t):
                parts.append(t)
            j += 1
        cues.append((start, " ".join(parts)))

    # word-level overlap dedup of rolling captions
    words = []  # (start, word)
    for start, text in cues:
        cw = text.split()
        maxk = min(len(words), len(cw), 40)
        best = 0
        for k in range(maxk, 0, -1):
            if [w for _, w in words[-k:]] == cw[:k]:
                best = k
                break
        for w in cw[best:]:
            words.append((start, w))

    out, buf, last = [], [], -(10**9)
    for start, w in words:
        if start - last >= chunk_seconds and buf:
            out.append(" ".join(buf)); buf = []
            out.append(f"[{_fmt(start)}]"); last = start
        elif last < 0:
            out.append(f"[{_fmt(start)}]"); last = start
        buf.append(w)
    if buf:
        out.append(" ".join(buf))
    return "\n".join(out)


def find_and_parse(download_dir: str, chunk_seconds: int = 30) -> str:
    """Find the first .vtt in download_dir and parse it. '' if none."""
    vtts = sorted(glob.glob(os.path.join(download_dir, "*.vtt")))
    if not vtts:
        return ""
    # prefer manual (en.vtt) over auto (en-orig.vtt) if both present
    vtts.sort(key=lambda p: ("orig" in os.path.basename(p), p))
    return parse_vtt(vtts[0], chunk_seconds)


if __name__ == "__main__":
    import sys
    print(parse_vtt(sys.argv[1]))
