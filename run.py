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

import config
from server.utils import logger
from server.app import run_server
from tunnel import cloudflare
from tunnel.keepalive import keep_alive_ping

LOGO = r"""
╔══════════════════════════════════════════════════════════╗
║                                                         ║
║   ██████╗██╗      █████╗ ██████╗  █████╗ ███╗   ██╗     ║
║  ██╔════╝██║     ██╔══██╗██╔══██╗██╔══██╗████╗  ██║     ║
║  ██║     ██║     ███████║██║  ██║███████║██╔██╗ ██║     ║
║  ██║     ██║     ██╔══██║██║  ██║██╔══██║██║╚██╗██║     ║
║  ╚██████╗███████╗██║  ██║██████╔╝██║  ██║██║ ╚████║     ║
║   ╚═════╝╚══════╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝     ║
║                                                         ║
║        O L L A M A   P R O X Y   S E R V E R            ║
║                                                         ║
╚══════════════════════════════════════════════════════════╝
"""


def parse_args():
    """Parse command-line arguments for config overrides."""
    parser = argparse.ArgumentParser(
        description="Kaggle Ollama Proxy Server",
        add_help=True,
    )
    parser.add_argument(
        "--models",
        type=str,
        default=None,
        help="Ollama model name (e.g. qwen3.6:27b)",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=None,
        help="Context window size",
    )
    parser.add_argument(
        "--keep-alive",
        type=str,
        default=None,
        help="Model keep-alive duration (e.g. 60m)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Server port",
    )
    parser.add_argument(
        "--no-think",
        action="store_true",
        default=False,
        help="Disable thinking/reasoning mode",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        default=False,
        help="Skip dependency installation step",
    )
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


def run_install_script():
    """Install all dependencies directly (replaces install.sh)."""
    devnull = open(os.devnull, "w")

    # Install zstd
    subprocess.run(
        ["sudo", "apt-get", "update", "-qq"],
        stdout=devnull, stderr=devnull, check=False,
    )
    subprocess.run(
        ["sudo", "apt-get", "install", "-y", "-qq", "zstd"],
        stdout=devnull, stderr=devnull, check=False,
    )

    # Install Ollama
    subprocess.run(
        ["curl", "-fsSL", "https://ollama.com/install.sh", "|", "sh"],
        shell=True,
        stdout=devnull, stderr=devnull, check=False,
    )

    # Download cloudflared
    cloudflared_url = config.CLOUDFLARED_URL
    try:
        urllib.request.urlretrieve(cloudflared_url, "cloudflared")
        os.chmod("cloudflared", 0o755)
    except Exception:
        pass

    # Install Python packages
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q",
         "fastapi", "uvicorn", "httpx", "orjson", "uvloop", "httptools"],
        stdout=devnull, stderr=devnull, check=False,
    )

    devnull.close()


def start_ollama():
    """Start Ollama serve as a background process."""
    devnull = open(os.devnull, "w")
    process = subprocess.Popen(
        ["ollama", "serve"],
        stdout=devnull,
        stderr=devnull,
    )
    time.sleep(3)
    return process


def pull_model():
    """Pull the Ollama model (output suppressed)."""
    devnull = open(os.devnull, "w")
    result = subprocess.run(
        ["ollama", "pull", config.OLLAMA_MODEL],
        stdout=devnull,
        stderr=devnull,
        check=False,
    )
    devnull.close()
    if result.returncode == 0:
        logger.info("✅ Model pulled successfully")
    else:
        logger.warning("⚠️ Model pull had errors, model may already be present")


def warm_model():
    """Load model into GPU memory and keep it warm."""
    logger.info(f"🔥 Warming up model {config.OLLAMA_MODEL} on GPU...")
    payload = json.dumps({
        "model": config.OLLAMA_MODEL,
        "prompt": ".",
        "options": {
            "num_predict": 1,
        },
    }).encode()

    req = urllib.request.Request(
        f"{config.OLLAMA_BASE_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        devnull = open(os.devnull, "w")
        with urllib.request.urlopen(req, timeout=300) as resp:
            devnull.write(resp.read().decode())
        devnull.close()
        logger.info("✅ Model loaded into GPU memory")
    except Exception as e:
        logger.warning(f"⚠️ Model warm failed: {e}")


def keep_model_warm():
    """Periodically send a request to keep the model loaded in GPU."""
    while True:
        time.sleep(config.KEEP_ALIVE.replace("m", "").replace("s", "").replace("h", ""))
        try:
            payload = json.dumps({
                "model": config.OLLAMA_MODEL,
                "prompt": ".",
                "options": {"num_predict": 1},
            }).encode()
            req = urllib.request.Request(
                f"{config.OLLAMA_BASE_URL}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with open(os.devnull, "w") as devnull:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    devnull.write(resp.read().decode())
        except Exception:
            pass


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


def main():
    args = parse_args()
    apply_config_overrides(args)
    ollama_process = None

    try:
        print(LOGO)

        if not args.skip_install:
            run_install_script()

        ollama_process = start_ollama()
        logger.info("✅ Ollama serve started")

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
            logger.info(f"\n{'=' * 60}")
            logger.info(f"✅ SERVER READY: {cloudflare.public_url}/v1")
            logger.info(f"{'=' * 60}")
        else:
            logger.error("❌ Tunnel not ready yet")

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
