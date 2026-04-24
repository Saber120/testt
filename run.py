#!/usr/bin/env python3
"""Main entry point for the Kaggle Ollama Proxy.

Orchestrates startup of Ollama, the FastAPI proxy server,
the Cloudflare tunnel, and the keep-alive mechanism.
"""

import os
import sys
import time
import json
import subprocess
import argparse
import threading
import urllib.request
import urllib.error
import shutil
import math

import config
from server.utils import logger
from server.app import run_server
from tunnel import cloudflare
from tunnel.keepalive import keep_alive_ping

# ─── Animated Logo ─────────────────────────────────────────────────────────────

LOGO_FRAMES = [
    r"""
          __     __   __    ______   __    __    __    ______   __   __
         /  \   /  \ /  \  /      \ /  |  /  |  /  \  /      \ /  | /  |
        /    \ /    /    \/  _____//   | /  /| /    \/  ____  \/  |/  /|
       /  /  |/  /|  /\   /\      ||  / /  / |/  /\   /      /|  / /  |/
      /  /    /  | /  | /  | \   \/  | /  /   /  | /  |  /  / /  |/  | /
     /__/    /__/|__/ |/__/  \____|/__/|__/   /__/|/__/  |__/ /__/|__/|/
     \      \   \    \       \     \   \     \    \     \     \   \    \
      \      \   \    \       \     \   \     \    \     \     \   \    \
       \______\___\____\_______\_____\___\______\____\_____\_____\___\____\
    """,
    r"""
     ███████╗██╗  ██╗   ██╗██╗  ██╗████████╗██╗   ██╗███╗   ██╗
     ██╔════╝██║  ██║   ██║██║ ██╔╝╚══██╔══╝██║   ██║████╗  ██║
     █████╗  ███████║   ██║█████╔╝    ██║   ██║   ██║██╔██╗ ██║
     ██╔══╝  ██╔══██║   ██║██╔═██╗    ██║   ██║   ██║██║╚██╗██║
     ██║     ██║  ██║   ██║██║  ██╗   ██║   ╚██████╔╝██║ ╚████║
     ╚═╝     ╚═╝  ╚═╝   ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═══╝
    """,
    r"""
    ▄▀▀ █▀▀ █░█ █▀▀  █░█ █░█ █▀▀  ▄▀▀ █▀▀ █▀▄ █▀█ █░█ █▀▀
    █░░ █░█ █▀█ █▀▀  █░█ █▄█ ▀▀█  █░░ █░░ █▀▄ █▀▀ █▀█ █▀▀
    ▀▀▀ ▀▀▀ ▀░▀ ▀▀▀  ▀▀▀ ▀░▀ ▀▀▀  ▀▀▀ ▀▀▀ ▀▀░ ▀░░ ▀░▀ ▀▀▀
    """,
    r"""
       ╔═══╗╔═╗╔═╗╔═══╗╔═══╗╔═══╗╔═══╗╔═══╗
       ║   ║║╔╣║╔╗║╚══╝║╔══╝║╔══╝║╔══╝║╔══╝
       ╚══╗║║║║╚╝║╔══╗╚╝╔╗ ║║╔═╗╚╝╔╗ ║╚══╗
       ╔══╝║║║║  ║║  ║  ║║ ║║╚═╝  ║║ ║╔══╝
       ╚═══╝╚╝╚╝ ╚══╝  ╚╝ ║╚══╝  ╚╝ ║╚═══╗
                          ╚══════════╝
    """,
]


def animate_logo():
    """Animated terminal logo with fade-in effect."""
    os.system("clear" if os.name != "nt" else "cls")

    final = r"""
    ╔══════════════════════════════════════════════════════════════════════════════╗
    ║                                                                            ║
    ║   ███████╗██╗  ██╗   ██╗██╗  ██╗████████╗██╗   ██╗███╗   ██╗               ║
    ║   ██╔════╝██║  ██║   ██║██║ ██╔╝╚══██╔══╝██║   ██║████╗  ██║               ║
    ║   █████╗  ███████║   ██║█████╔╝    ██║   ██║   ██║██╔██╗ ██║               ║
    ║   ██╔══╝  ██╔══██║   ██║██╔═██╗    ██║   ██║   ██║██║╚██╗██║               ║
    ║   ██║     ██║  ██║   ██║██║  ██╗   ██║   ╚██████╔╝██║ ╚████║               ║
    ║   ╚═╝     ╚═╝  ╚═╝   ╚═╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═══╝               ║
    ║                                                                            ║
    ║   ▄▀▀ █▀▀ █░█ █▀▀  ▄▀▀ █▀▀ █▀▄ █▀█ █░█   OpenAI-Compatible Proxy        ║
    ║   █░░ █░█ █▀█ █▀▀  █░░ █░░ █▀▄ █▀▀ █▀█   Kaggle GPU → Public API        ║
    ║   ▀▀▀ ▀▀▀ ▀░▀ ▀▀▀  ▀▀▀ ▀▀▀ ▀▀░ ▀░░ ▀░▀                                 ║
    ║                                                                            ║
    ║   🚀 Free LLM API for VS Code, Cursor, OpenCode, Claude Code, and more     ║
    ║                                                                            ║
    ╚══════════════════════════════════════════════════════════════════════════════╝"""

    for frame in LOGO_FRAMES:
        print(frame)
        time.sleep(0.3)
        print("\033[F" * frame.count("\n"), end="\r\n" * frame.count("\n"))

    for i in range(0, len(final) + 1, 12):
        chunk = final[i:i + 12]
        if chunk:
            print(chunk, end="", flush=True)
            time.sleep(0.02)
    print("\n")


# ─── Progress Bar ──────────────────────────────────────────────────────────────

class ProgressBar:
    """Simple terminal progress bar."""

    def __init__(self, label, length=30):
        self.label = label
        self.length = length
        self._width = shutil.get_terminal_size((80, 24)).columns or 80
        self._update(0, "...")

    def _update(self, pct, status=""):
        filled = int(self.length * pct / 100)
        bar = "█" * filled + "░" * (self.length - filled)
        line = f"  [{bar}] {pct:3d}%  {status}"
        pad = max(0, self._width - len(line) - 1)
        print(f"\r{line}{' ' * pad}", end="", flush=True)

    def step(self, pct, status=""):
        self._update(pct, status)

    def done(self, status="Done"):
        self._update(100, status)
        print()

    def fail(self, status="Failed"):
        self._update(100, f"❌ {status}")
        print()


def _download_with_progress(url, dest, label="Downloading"):
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


def _run_with_progress(cmd, label, shell=False):
    """Run a command with a progress bar (shows elapsed time as proxy)."""
    bar = ProgressBar(label)
    start = time.time()
    try:
        result = subprocess.run(
            cmd, shell=shell,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        bar.done(f"✅ {label}")
        return result
    except Exception:
        bar.fail(label)
        return None


# ─── Install ──────────────────────────────────────────────────────────────────

def run_install_script():
    """Install all dependencies with progress bars."""
    print("\n  ── Installing dependencies ──\n")

    # 1. apt-get update
    bar = ProgressBar("Updating apt")
    subprocess.run(["sudo", "apt-get", "update", "-qq"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    bar.done("apt updated")

    # 2. Install zstd
    bar = ProgressBar("Installing zstd")
    subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "zstd"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    bar.done("zstd installed")

    # 3. Install Ollama
    bar = ProgressBar("Installing Ollama")
    subprocess.run(
        "curl -fsSL https://ollama.com/install.sh | sh",
        shell=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    bar.done("Ollama installed")

    # 4. Download cloudflared
    bar = ProgressBar("Downloading cloudflared")
    try:
        _download_with_progress(config.CLOUDFLARED_URL, "cloudflared", "cloudflared")
        os.chmod("cloudflared", 0o755)
    except Exception:
        bar.fail("cloudflared download")

    # 5. Python packages
    bar = ProgressBar("Installing Python deps")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q",
         "fastapi", "uvicorn", "httpx", "orjson", "uvloop", "httptools"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    bar.done("Python packages ready")
    print()


# ─── Ollama ───────────────────────────────────────────────────────────────────

def start_ollama():
    """Start Ollama serve as a background process."""
    bar = ProgressBar("Starting Ollama")
    devnull = open(os.devnull, "w")
    process = subprocess.Popen(["ollama", "serve"], stdout=devnull, stderr=devnull)
    time.sleep(3)
    bar.done("Ollama running on :11434")
    devnull.close()
    return process


def pull_model():
    """Pull the Ollama model with progress bar."""
    bar = ProgressBar(f"Pulling {config.OLLAMA_MODEL}")
    result = subprocess.run(
        ["ollama", "pull", config.OLLAMA_MODEL],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    )
    if result.returncode == 0:
        bar.done("Model ready")
    else:
        bar.done("Model already present (or pull skipped)")


def warm_model():
    """Load model into GPU memory."""
    bar = ProgressBar(f"Warming {config.OLLAMA_MODEL}")
    payload = json.dumps({
        "model": config.OLLAMA_MODEL,
        "prompt": ".",
        "options": {"num_predict": 1},
    }).encode()

    req = urllib.request.Request(
        f"{config.OLLAMA_BASE_URL}/api/generate",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            resp.read()
        bar.done("Model loaded into GPU")
    except Exception as e:
        bar.fail(f"warm failed: {e}")


def keep_model_warm():
    """Periodically send a request to keep the model loaded in GPU."""
    while True:
        time.sleep(int(config.KEEP_ALIVE.replace("m", "").replace("s", "").replace("h", "")))
        try:
            payload = json.dumps({
                "model": config.OLLAMA_MODEL,
                "prompt": ".",
                "options": {"num_predict": 1},
            }).encode()
            req = urllib.request.Request(
                f"{config.OLLAMA_BASE_URL}/api/generate",
                data=payload, headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
        except Exception:
            pass


# ─── Shutdown ─────────────────────────────────────────────────────────────────

def shutdown(ollama_process):
    """Gracefully shut down all components."""
    logger.info("🛑 Shutting down...")
    if cloudflare.tunnel_process:
        try:
            cloudflare.tunnel_process.terminate()
            cloudflare.tunnel_process.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass
    if ollama_process:
        try:
            ollama_process.terminate()
            ollama_process.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            pass
    logger.info("✅ Shutdown complete")


# ─── Main ─────────────────────────────────────────────────────────────────────

def is_notebook():
    """Detect if running inside Jupyter/Kaggle notebook."""
    try:
        get_ipython  # noqa: F821
        return True
    except NameError:
        return False


def parse_args():
    """Parse command-line arguments for config overrides."""
    parser = argparse.ArgumentParser(description="Kaggle Ollama Proxy Server")
    parser.add_argument("--models", type=str, default=None,
                        help="Ollama model name (e.g. qwen3.6:27b)")
    parser.add_argument("--num-ctx", type=int, default=None, help="Context window size")
    parser.add_argument("--keep-alive", type=str, default=None, help="Keep-alive duration")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    parser.add_argument("--no-think", action="store_true", default=False,
                        help="Disable thinking mode")
    parser.add_argument("--skip-install", action="store_true", default=False,
                        help="Skip dependency installation")
    parser.add_argument("--detach", action="store_true", default=False,
                        help="Run in background (detach from cell/terminal)")
    return parser.parse_args()


def apply_config_overrides(args):
    """Apply CLI argument overrides to config module."""
    if args.models:
        config.OLLAMA_MODEL = args.models
    if args.num_ctx:
        config.NUM_CTX = args.num_ctx
        config.NUM_PREDICT = args.num_ctx
    if args.keep_alive:
        config.KEEP_ALIVE = args.keep_alive
    if args.port:
        config.SERVER_PORT = args.port
    if args.no_think:
        config.THINK_ENABLED = False


def _run_everything():
    """Core startup logic (runs in main thread or background thread)."""
    ollama_process = None

    if not SKIP_INSTALL:
        run_install_script()

    ollama_process = start_ollama()
    pull_model()
    warm_model()

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(3)
    logger.info("✅ FastAPI is ready")

    watchdog_thread = threading.Thread(target=cloudflare.tunnel_watchdog, daemon=True)
    watchdog_thread.start()

    keepalive_thread = threading.Thread(target=keep_alive_ping, daemon=True)
    keepalive_thread.start()

    warm_thread = threading.Thread(target=keep_model_warm, daemon=True)
    warm_thread.start()

    time.sleep(10)
    if cloudflare.public_url:
        print(f"\n  {'=' * 60}")
        print(f"  ✅ SERVER READY: {cloudflare.public_url}/v1")
        print(f"  {'=' * 60}\n")
    else:
        logger.error("❌ Tunnel not ready yet")

    return ollama_process


SKIP_INSTALL = False


def main():
    global SKIP_INSTALL
    args = parse_args()
    apply_config_overrides(args)
    SKIP_INSTALL = args.skip_install
    running_in_notebook = is_notebook()

    animate_logo()

    if running_in_notebook or args.detach:
        # ── Detach mode: start everything in a daemon thread, return immediately ──
        bg = threading.Thread(target=_run_everything, daemon=True)
        bg.start()
        print("  📓 Running in background — cell/terminal is free.\n")
        print("  Your server will appear at:")
        print("  http://localhost:8000/v1")
        print("  (Cloudflare tunnel URL will be printed by the server)")
        print()
        # Small delay so logs are visible before cell returns
        time.sleep(2)
        return

    # ── Attached mode: block and run forever ──
    ollama_process = None
    try:
        ollama_process = _run_everything()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown(ollama_process)
    except Exception as e:
        logger.error(f"💥 Unexpected error: {e}")
        if ollama_process:
            shutdown(ollama_process)
        raise


if __name__ == "__main__":
    main()