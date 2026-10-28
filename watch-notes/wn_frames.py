#!/usr/bin/env python3
"""
wn_frames.py: keyframe extraction via interval-sample + perceptual-hash dedup.

The robust alternative to raw ffmpeg scene-detection: sample one frame every
`interval` seconds (so no slide is ever missed), then keep a frame only if its
perceptual hash is far enough from the last kept frame (so duplicates, minor
motion, and slide-build animations collapse to one frame per distinct slide).

Run standalone to eyeball what it picks:
    python wn_frames.py /path/to/video.mp4 --label talk --out /tmp/kf
"""
from __future__ import annotations
import argparse, glob, os, shutil, subprocess, sys, tempfile
from PIL import Image
import imagehash


def to_seconds(t: str | None) -> float | None:
    if t is None:
        return None
    if ":" not in str(t):
        return float(t)
    parts = [float(p) for p in str(t).split(":")]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def hhmmss(sec: float) -> str:
    s = int(sec)
    return f"{s//3600:02d}{(s%3600)//60:02d}{s%60:02d}"


def extract_keyframes(
    video: str,
    out_dir: str,
    label: str = "slide",
    interval: float = 3.0,
    hash_threshold: int = 5,
    max_frames: int = 60,
    start: str | None = None,
    end: str | None = None,
):
    """Return list of (timestamp_sec, saved_relpath). Saves JPEGs into out_dir."""
    workdir = tempfile.mkdtemp(prefix="wnframes-")
    try:
        # 1. sample one candidate frame every `interval` seconds
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        if start is not None:
            cmd += ["-ss", str(start)]
        if end is not None:
            cmd += ["-to", str(end)]
        cmd += ["-i", video, "-vf", f"fps=1/{interval}",
                os.path.join(workdir, "cand_%05d.jpg")]
        subprocess.run(cmd, check=True)

        cands = sorted(glob.glob(os.path.join(workdir, "cand_*.jpg")))
        offset = to_seconds(start) or 0.0

        # 2. perceptual-hash dedup: keep a frame only if visually distinct
        kept = []  # (timestamp_sec, candidate_path, hash)
        last_hash = None
        for idx, fp in enumerate(cands):
            ts = idx * interval + offset
            try:
                h = imagehash.phash(Image.open(fp))
            except Exception:
                continue
            if last_hash is None or (h - last_hash) > hash_threshold:
                kept.append((ts, fp, h))
                last_hash = h

        # 3. cap: if over budget, greedily keep the most-distinct frames
        if len(kept) > max_frames:
            scored = [(0.0, kept[0])]
            for i in range(1, len(kept)):
                scored.append((kept[i][2] - kept[i - 1][2], kept[i]))
            scored.sort(key=lambda x: x[0], reverse=True)
            keep_set = {id(k[1]) for k in scored[:max_frames]}
            kept = [k for k in kept if id(k) in keep_set]
            kept.sort(key=lambda k: k[0])

        # 4. save out
        os.makedirs(out_dir, exist_ok=True)
        manifest = []
        for i, (ts, fp, _h) in enumerate(kept, 1):
            name = f"{label}-{i:03d}-t{hhmmss(ts)}.jpg"
            shutil.copy(fp, os.path.join(out_dir, name))
            manifest.append((ts, name))
        return manifest
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out", default="/tmp/wn-kf")
    ap.add_argument("--label", default="slide")
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--hash-threshold", type=int, default=5)
    ap.add_argument("--max-frames", type=int, default=60)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    args = ap.parse_args()

    m = extract_keyframes(
        args.video, args.out, args.label, args.interval,
        args.hash_threshold, args.max_frames, args.start, args.end,
    )
    print(f"kept {len(m)} frames -> {args.out}")
    for ts, name in m:
        print(f"  [{int(ts)//60:02d}:{int(ts)%60:02d}]  {name}")


if __name__ == "__main__":
    main()
