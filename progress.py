"""Progress bar and download helpers."""

import subprocess
import time
import shutil
import threading
import urllib.request


class ProgressBar:
    """Simple terminal progress bar."""

    def __init__(self, label, length=30):
        self.label = label
        self.length = length
        self._pct = 0
        self._status = ""
        self._done = False
        self._width = shutil.get_terminal_size((80, 24)).columns or 80
        self._lock = threading.Lock()
        self._render()

    def _render(self):
        with self._lock:
            if self._done:
                return
            filled = int(self.length * self._pct / 100)
            bar = "\u2588" * filled + "\u2591" * (self.length - filled)
            line = f"  [{bar}] {self._pct:3d}%  {self._status}"
            pad = max(0, self._width - len(line) - 1)
            print(f"\r{line}{' ' * pad}", end="", flush=True)

    def step(self, pct, status=""):
        self._pct = min(100, max(0, pct))
        self._status = status
        self._render()

    def done(self, status="Done"):
        self._done = True
        self._pct = 100
        self._status = status
        self._render()
        print()

    def fail(self, status="Failed"):
        self._done = True
        self._pct = 100
        self._status = f"\u274c {status}"
        self._render()
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
    """Run a command with a progress bar (shows spinner during execution)."""
    bar = ProgressBar(label)
    spins = ["|", "/", "-", "\\"]
    idx = [0]

    def spinner():
        while not bar._done:
            time.sleep(0.4)
            idx[0] = (idx[0] + 1) % len(spins)
            with bar._lock:
                filled = int(bar.length * bar._pct / 100)
                bar_str = "\u2588" * filled + "\u2591" * (bar.length - filled)
                line = f"  [{bar_str}] {bar._pct:3d}%  {spins[idx[0]]} {label}.."
                pad = max(0, bar._width - len(line) - 1)
                print(f"\r{line}{' ' * pad}", end="", flush=True)

    thread = threading.Thread(target=spinner, daemon=True)
    thread.start()

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
