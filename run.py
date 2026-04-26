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

# ── Install deps FIRST before any third-party imports ──

def _ensure_deps(args):
    """Install system + Python dependencies before anything else."""
    from installer import run_install_script
    from progress import IndeterminateBar

    skip = getattr(args, "skip_install", False)
    if not skip:
        run_install_script()


def _parse_args_early():
    """Minimal arg parse just to check --skip-install."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-install", action="store_true", default=False)
    parser.add_argument("--models", type=str, default=None)
    parser.add_argument("--num-ctx", type=int, default=None)
    parser.add_argument("--keep-alive", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-think", action="store_true", default=False)
    return parser.parse_args()


_early_args = _parse_args_early()
_ensure_deps(_early_args)

# ── Now safe to import everything ──

import config
from server.utils import logger
from server.app import run_server
from tunnel import cloudflare
from tunnel.keepalive import keep_alive_ping
from logo import animate_logo
from progress import LineProgressBar, IndeterminateBar
from installer import run_install_script


# ─── Ollama ───────────────────────────────────────────────────────────────────

def start_ollama():
    """Start Ollama serve as a background process."""
    bar = IndeterminateBar("Starting Ollama")
    devnull = open(os.devnull, "w")
    try:
        process = subprocess.Popen(["ollama", "serve"], stdout=devnull, stderr=devnull)
    except Exception:
        devnull.close()
        raise
    time.sleep(3)
    bar.done("Ollama running on :11434")
    devnull.close()
    return process


def pull_model():
    """Pull the Ollama model with a progress bar from Ollama's JSON output."""
    print()
    bar = LineProgressBar(f"Pulling {config.OLLAMA_MODEL}")
    proc = subprocess.Popen(
        ["ollama", "pull", config.OLLAMA_MODEL],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    last_pct = -1
    last_status = ""
    raw = proc.stderr.readline()
    while raw:
        line = raw.strip()
        if line:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                pass
            else:
                total = data.get("total", 0)
                completed = data.get("completed", 0)
                status = data.get("status", "")
                if total and completed:
                    pct = int(completed * 100 / total)
                    mb_done = completed // (1024 * 1024)
                    mb_total = total // (1024 * 1024)
                    bar.step(pct, f"{status}  {mb_done}MB/{mb_total}MB")
                else:
                    bar.spin(status)
                last_pct = pct if total and completed else last_pct
                last_status = status
        raw = proc.stderr.readline()

    proc.wait()
    bar.done(f"{config.OLLAMA_MODEL} ready")


def _warm_request(model, timeout=300):
    """Send a warm request to keep the model loaded in GPU memory."""
    payload = json.dumps({
        "model": model,
        "prompt": ".",
        "options": {"num_predict": 1},
    }).encode()
    req = urllib.request.Request(
        f"{config.OLLAMA_BASE_URL}/api/generate",
        data=payload, headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        resp.read()


def warm_model():
    """Load model into GPU memory."""
    bar = IndeterminateBar(f"Warming {config.OLLAMA_MODEL}")
    try:
        _warm_request(config.OLLAMA_MODEL, timeout=300)
        bar.done("Model loaded into GPU")
    except Exception as e:
        bar.fail(f"warm failed: {e}")


def cleanup():
    """Kill stale processes and reset global state for clean startup."""
    logger.info("🧹 Cleaning up previous instances...")
    subprocess.run(["pkill", "-f", "ollama serve"], capture_output=True)
    subprocess.run(["pkill", "-f", "cloudflared"], capture_output=True)
    subprocess.run(["pkill", "-f", "uvicorn"], capture_output=True)
    time.sleep(1)

    # Reset tunnel state
    cloudflare.tunnel_process = None
    cloudflare.public_url = None

    # Remove stale tunnel URL file
    try:
        os.remove("tunnel_url.txt")
    except FileNotFoundError:
        pass

    logger.info("✅ Cleanup complete")


def _parse_keep_alive_duration(duration_str: str) -> int:
    """Parse a keep-alive duration string into seconds."""
    s = duration_str.lower()
    if s.endswith("m"):
        return int(s[:-1]) * 60
    elif s.endswith("h"):
        return int(s[:-1]) * 3600
    elif s.endswith("s"):
        return int(s[:-1])
    else:
        return int(s)


def _is_model_loaded(model: str) -> bool:
    """Check if the model is currently loaded in Ollama."""
    try:
        req = urllib.request.Request(
            f"{config.OLLAMA_BASE_URL}/api/tags", method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            for m in data.get("models", []):
                if m.get("name") == model:
                    loaded_models = m.get("loaded_at")
                    if loaded_models:
                        return True
    except Exception:
        pass
    return False


def keep_model_warm():
    """Periodically send a request to keep the model loaded in GPU."""
    wait_seconds = _parse_keep_alive_duration(config.KEEP_ALIVE)
    while True:
        time.sleep(wait_seconds)
        if not _is_model_loaded(config.OLLAMA_MODEL):
            try:
                _warm_request(config.OLLAMA_MODEL, timeout=60)
            except Exception:
                pass


# ─── Shutdown ─────────────────────────────────────────────────────────────────

def _safe_terminate(proc):
    """Terminate a process, killing it if it doesn't respond."""
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    except OSError:
        pass


def shutdown(ollama_process):
    """Gracefully shut down all components."""
    logger.info("🛑 Shutting down...")
    _safe_terminate(cloudflare.tunnel_process)
    _safe_terminate(ollama_process)
    logger.info("✅ Shutdown complete")


# ─── Main ─────────────────────────────────────────────────────────────────────

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

    cleanup()

    ollama_process = start_ollama()

    # Start the FastAPI server early so health checks pass in notebook mode
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(2)
    logger.info("✅ FastAPI is ready")

    pull_model()
    warm_model()

    watchdog_thread = threading.Thread(target=cloudflare.tunnel_watchdog, daemon=True)
    watchdog_thread.start()

    keepalive_thread = threading.Thread(target=keep_alive_ping, daemon=True)
    keepalive_thread.start()

    warm_thread = threading.Thread(target=keep_model_warm, daemon=True)
    warm_thread.start()

    # Wait for tunnel to be ready and verify it's alive
    import urllib.request as _urllib
    max_wait = 90
    start_time = time.time()
    alive = False
    while time.time() - start_time < max_wait:
        if cloudflare.public_url:
            try:
                req = _urllib.Request(f"{cloudflare.public_url}/v1", method="HEAD")
                with _urllib.urlopen(req, timeout=5) as resp:
                    if resp.status < 500:
                        alive = True
                        break
            except Exception:
                pass
        time.sleep(2)

    if not alive and cloudflare.public_url:
        logger.warning("⚠️ Tunnel link dead, restarting cloudflared...")
        cloudflare.tunnel_process = None
        cloudflare.public_url = None
        cloudflare.start_tunnel()
        time.sleep(5)
        alive = cloudflare.public_url is not None

    if alive and cloudflare.public_url:
        print(f"\n  {'=' * 60}")
        print(f"  ✅ SERVER READY: {cloudflare.public_url}/v1")
        print(f"  {'=' * 60}\n")
    else:
        logger.error("❌ Tunnel not ready after timeout")

    return ollama_process


SKIP_INSTALL = False


def main():
    global SKIP_INSTALL
    args = parse_args()
    apply_config_overrides(args)
    SKIP_INSTALL = args.skip_install

    # Already installed at module load time, don't run again

    animate_logo()

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
