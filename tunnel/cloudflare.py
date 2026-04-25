"""Cloudflare tunnel management for public endpoint exposure.

Starts and monitors a Cloudflare tunnel process, providing a public
URL that proxies to the local FastAPI server.
"""

import os
import re
import signal
import select
import subprocess
import time
import threading

import config
from server.utils import logger

tunnel_process = None
public_url = None


def drain_process_output(proc, name="tunnel"):
    """Drain stdout from a subprocess, logging output at debug level."""
    while proc.poll() is None:
        try:
            line = proc.stdout.readline()
            if line:
                line_stripped = line.strip()
                if line_stripped:
                    logger.debug(f"[{name}] {line_stripped}")
            else:
                time.sleep(0.5)
        except Exception:
            break
    logger.warning(f"⚠️ [{name}] Output drain ended (process likely dead)")


def start_tunnel():
    global public_url
    subprocess.run(["pkill", "-f", "cloudflared"], capture_output=True)
    time.sleep(2)

    proc = subprocess.Popen(
        [config.CLOUDFLARED_BINARY, "tunnel", "--url", f"http://localhost:{config.SERVER_PORT}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    url = None
    start = time.time()
    readline_lock = threading.Lock()
    while time.time() - start < config.TUNNEL_START_TIMEOUT:
        with readline_lock:
            if proc.poll() is not None:
                logger.error("❌ cloudflared died during startup")
                return None, None
            ready, _, _ = select.select([proc.stdout], [], [], 2.0)
            if not ready:
                continue
            line = proc.stdout.readline()
        if not line:
            continue
        if "trycloudflare.com" in line:
            match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", line)
            if match:
                url = match.group(0)
                break

    if url:
        public_url = url
        with open("tunnel_url.txt", "w") as f:
            f.write(url)

    return proc, url


def tunnel_watchdog():
    global tunnel_process, public_url
    restart_count = 0
    max_restarts = config.TUNNEL_MAX_RESTARTS

    while restart_count < max_restarts:
        proc, url = start_tunnel()

        if proc is None or url is None:
            logger.error(f"❌ Tunnel failed (attempt {restart_count + 1})")
            restart_count += 1
            time.sleep(10)
            continue

        restart_count = 0
        tunnel_process = proc

        drain_thread = threading.Thread(
            target=drain_process_output,
            args=(proc, "cloudflared"),
            daemon=True,
        )
        drain_thread.start()

        while proc.poll() is None:
            time.sleep(config.TUNNEL_POLL_INTERVAL)

        logger.warning("⚠️ cloudflared DIED! Restarting in 5s...")
        time.sleep(config.TUNNEL_RESTART_DELAY)
        restart_count += 1

    logger.error("💀 Tunnel watchdog giving up")
