"""Get the user's attention: a macOS notification plus a terminal bell. Never raises."""
import subprocess
import sys


def ping(title, text):
    try:
        sys.stderr.write("\a")
        sys.stderr.flush()
        if sys.platform == "darwin":
            esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(["osascript", "-e", f'display notification "{esc(text)}" with title "{esc(title)}"'],
                           capture_output=True, timeout=5)
    except Exception:
        pass
