"""Progress bar and download helpers."""

import subprocess
import shutil
import urllib.request


class ProgressBar:
    """Simple terminal progress bar."""

    def __init__(self, label, length=30):
        self.label = label
        self.length = length
        self._width = shutil.get_terminal_size((80, 24)).columns or 80
        self._update(0, ".")

    def _update(self, pct, status=""):
        filled = int(self.length * pct / 100)
        bar = "\u2588" * filled + "\u2591" * (self.length - filled)
        line = f"  [{bar}] {pct:3d}%  {status}"
        pad = max(0, self._width - len(line) - 1)
        print(f"\r{line}{' ' * pad}", end="", flush=True)

    def step(self, pct, status=""):
        self._update(pct, status)

    def done(self, status="Done"):
        self._update(100, status)
        print()

    def fail(self, status="Failed"):
        self._update(100, f"\u274c {status}")
        print()


def download_with_progress(url, dest, label="Downloading"):
    """Download a file with a progress bar."""
    bar = ProgressBar(label)
    try:
        with urllib.request.urlopen(url) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = min(100, int(downloaded * 100 / total))
                        bar.step(pct, f"{downloaded // 1024 // 1024}MB / {total // 1024 // 1024}MB")
                    else:
                        bar.step(50, f"{downloaded // 1024 // 1024}MB")
            bar.done(f"{label} complete")
    except Exception:
        bar.fail(label)


def run_with_progress(cmd, label, shell=False):
    """Run a command with a progress bar (shows elapsed time as proxy)."""
    bar = ProgressBar(label)
    try:
        result = subprocess.run(
            cmd, shell=shell,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        bar.done(f"\u2705 {label}")
        return result
    except Exception:
        bar.fail(label)
        return None
