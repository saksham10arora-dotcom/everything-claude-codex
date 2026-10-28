#!/usr/bin/env python3
"""
wn_gather.py: gather the raw materials for a video note, WITHOUT writing the
note. Downloads the video, extracts perceptual-hash keyframes, fetches the
transcript, and prints a JSON manifest. The note itself is written separately
(by Claude / a Haiku subagent) reading these materials: so note-writing runs on
the Claude plan instead of fighting congested free VLM APIs.

Usage:
  python wn_gather.py <youtube-url-or-id> --label ep2 --out-dir <notes-folder>
"""
import argparse, glob, json, os, shutil, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wn_frames


def download(url, workdir):
    out = os.path.join(workdir, "v.%(ext)s")
    subprocess.run(["yt-dlp", "--no-warnings", "--retries", "5", "--sleep-requests",
                    "1.5", "-o", out, "-S", "res:720", "--write-info-json", url], check=True)
    vids = [f for f in glob.glob(os.path.join(workdir, "v.*"))
            if f.rsplit(".", 1)[-1] in ("mp4", "mkv", "webm")]
    if not vids:
        sys.exit("ERROR: no video downloaded")
    return vids[0]


def meta(workdir):
    js = glob.glob(os.path.join(workdir, "*.info.json"))
    if not js:
        return {}
    d = json.load(open(js[0]))
    return {"title": d.get("title", ""), "author": d.get("uploader", ""),
            "url": d.get("webpage_url", ""), "id": d.get("id", ""),
            "duration": d.get("duration", 0)}


def transcript(vid, path):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        tr = next(iter(api.list(vid)))
        lines, last = [], -999
        for sn in tr.fetch():
            s = int(sn.start)
            if s - last >= 30:
                lines.append(f"\n[{s//60:02d}:{s%60:02d}] "); last = s
            lines.append(sn.text)
        open(path, "w").write(" ".join(lines))
        return tr.language_code
    except Exception as e:
        open(path, "w").write("")
        return f"(none: {type(e).__name__})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--label", default="vid")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-frames", type=int, default=8)
    a = ap.parse_args()

    img = os.path.join(a.out_dir, "hover-notes-images")
    os.makedirs(img, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="gather-")
    try:
        url = a.url if a.url.startswith("http") else f"https://www.youtube.com/watch?v={a.url}"
        vid = download(url, tmp)
        m = meta(tmp)
        frames = wn_frames.extract_keyframes(vid, img, a.label, 3.0, 5, a.max_frames)
        tpath = f"/tmp/{a.label}-transcript.txt"
        lang = transcript(m.get("id", ""), tpath)
        print(json.dumps({
            "meta": m,
            "transcript_path": tpath,
            "transcript_lang": lang,
            "frames": [{"time": f"{int(ts)//60:02d}:{int(ts)%60:02d}",
                        "embed": f"hover-notes-images/{n}",
                        "abspath": os.path.join(img, n)} for ts, n in frames],
        }, indent=2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
