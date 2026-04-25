"""Multi-line progress system — each task gets its own line."""

import subprocess
import time
import shutil
import threading
import urllib.request


class LineProgressBar:
    """A progress bar that owns one terminal line and never overlaps."""

    def __init__(self, label, length=30):
        self.label = label
        self.length = length
        self._pct = 0
        self._status = ""
        self._done = False
        self._width = shutil.get_terminal_size((80, 24)).columns or 80
        self._lock = threading.Lock()
        self._spin_idx = 0
        self._spins = ["|", "/", "-", "\\"]
        # Print the initial line
        self._render()

    def _render(self):
        with self._lock:
            filled = int(self.length * self._pct / 100)
            bar = "\u2588" * filled + "\u2591" * (self.length - filled)
            if self._pct == 100 and self._done:
                indicator = "\u2705"
            else:
                indicator = self._spins[self._spin_idx % len(self._spins)]
            line = f"  [{bar}] {self._pct:3d}%  {indicator} {self._status}"
            pad = max(0, self._width - len(line) - 1)
            print(f"\r{line}{' ' * pad}", end="", flush=True)

    def step(self, pct, status=""):
        """Update percentage and status text."""
        self._pct = min(100, max(0, pct))
        self._status = status
        self._render()

    def spin(self, status=""):
        """Update status and advance spinner for indeterminate work."""
        self._spin_idx += 1
        self._status = status
        self._render()

    def done(self, status="Done"):
        self._done = True
        self._pct = 100
        self._status = status
        self._render()
        print()  # Move to next line

    def fail(self, status="Failed"):
        self._done = True
        self._pct = 0
        self._status = f"\u274c {status}"
        self._render()
        print()


class IndeterminateBar:
    """Animated bar for tasks with no progress info — manages its own thread."""

    def __init__(self, label, length=30):
        self.label = label
        self.length = length
        self._done = False
        self._width = shutil.get_terminal_size((80, 24)).columns or 80
        self._lock = threading.Lock()
        self._pos = 0
        self._direction = 1
        print(f"  {' ' * self.length}   0%  {label}..", flush=True)
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()

    def _render(self):
        with self._lock:
            if self._done:
                return
            right = min(self.length - 1, max(0, self._pos))
            bar_chars = [" "] * self.length
            bar_chars[right] = "\u25cf"
            bar = "".join(bar_chars)
            line = f"  [{bar}]     \u2192  {self.label}.."
            pad = max(0, self._width - len(line) - 1)
            print(f"\r{line}{' ' * pad}", end="", flush=True)

    def _animate(self):
        while not self._done:
            self._pos += self._direction
            if self._pos >= self.length or self._pos <= 0:
                self._direction *= -1
            self._render()
            time.sleep(0.15)

    def done(self, status="Done"):
        self._done = True
        block = "\u2588" * self.length
        line = f"  [{block}]  100%  \u2705 {status}"
        pad = max(0, self._width - len(line) - 1)
        print(f"\r{line}{' ' * pad}", flush=True)
        print()

    def fail(self, status="Failed"):
        self._done = True
        block = "\u2588" * self.length
        line = f"  [{block}]   0%  \u274c {status}"
        pad = max(0, self._width - len(line) - 1)
        print(f"\r{line}{' ' * pad}", flush=True)
        print()


def download_with_progress(url, dest, label="Downloading"):
    """Download a file with a dedicated line progress bar."""
    bar = LineProgressBar(label)
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
                        mb_done = downloaded // (1024 * 1024)
                        mb_total = total // (1024 * 1024)
                        bar.step(pct, f"{mb_done}MB / {mb_total}MB")
                    else:
                        mb_cur = downloaded // (1024 * 1024)
                        bar.spin(f"{mb_cur}MB")
            bar.done(f"{label} complete")
    except Exception:
        bar.fail(label)


def run_with_progress(cmd, label, shell=False):
    """Run a command with an indeterminate animated bar (dedicated line)."""
    bar = IndeterminateBar(label)

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