#!/usr/bin/env python3
"""Main entry point for the Kaggle Ollama Proxy.

Orchestrates startup of Ollama, the FastAPI proxy server,
the Cloudflare tunnel, and the keep-alive mechanism.
"""

import os
import time
import subprocess
import threading

import config
from server.utils import logger
from server.app import run_server
from tunnel import cloudflare
from tunnel.keepalive import keep_alive_ping


def run_install_script():
    """Run the installation script for system dependencies."""
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "install.sh")
    logger.info("📦 Running installation script...")
    result = subprocess.run(["bash", script_path], check=False)
    if result.returncode != 0:
        logger.warning("⚠️ Installation script had errors, continuing anyway...")


def start_ollama():
    """Start Ollama serve as a background process."""
    logger.info("🚀 Starting Ollama serve...")
    process = subprocess.Popen(["ollama", "serve"])
    time.sleep(3)
    logger.info("✅ Ollama serve started")
    return process


def pull_model():
    """Pull the Ollama model."""
    logger.info(f"📥 Pulling model {config.OLLAMA_MODEL}...")
    result = subprocess.run(["ollama", "pull", config.OLLAMA_MODEL], check=False)
    if result.returncode == 0:
        logger.info("✅ Model pulled successfully")
    else:
        logger.warning("⚠️ Model pull had errors, model may already be present")


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
    ollama_process = None

    try:
        # Step 1: Install dependencies
        run_install_script()

        # Step 2: Start Ollama
        ollama_process = start_ollama()

        # Step 3: Pull model
        pull_model()

        # Step 4: Start FastAPI server in background thread
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        time.sleep(3)
        logger.info("✅ FastAPI is ready")

        # Step 5: Start tunnel watchdog
        watchdog_thread = threading.Thread(target=cloudflare.tunnel_watchdog, daemon=True)
        watchdog_thread.start()

        # Step 6: Start keep-alive ping
        keepalive_thread = threading.Thread(target=keep_alive_ping, daemon=True)
        keepalive_thread.start()

        # Step 7: Wait and report status
        time.sleep(10)
        if cloudflare.public_url:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"✅ SERVER READY: {cloudflare.public_url}/v1")
            logger.info(f"{'=' * 60}")
        else:
            logger.error("❌ Tunnel not ready yet")

        # Keep main thread alive
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
