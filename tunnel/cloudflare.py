"""Cloudflare tunnel management for public endpoint exposure.

Starts and monitors a Cloudflare tunnel process, providing a public
URL that proxies to the local FastAPI server.
"""

import re
import time
import os
import signal
import select
import subprocess
import threading

import config
from server.utils import logger

tunnel_process = None
public_url = None


def drain_process_output(proc, name="tunnel"):
    """Drain stdout from a subprocess, logging output at debug level.

    Args:
        proc: Subprocess.Popen instance to read from.
        name: Label for log messages.
    """
    while proc.poll() is None:
        try:
            line = proc.stdout.readline()
            if line:
                line_stripped = line.strip()
                if line_stripped:
                    logger.debug(f"[{name}] {line_stripped}")
            else:
                time.sleep(0.5)
        except (IOError, OSError, ValueError):
            break
    logger.warning(f"⚠️ [{name}] Output drain ended (process likely dead)")


def start_tunnel():
    global public_url
    subprocess.run(["pkill", "-f", "cloudflared"], capture_output=True)
    time.sleep(2)

    log_file = open("cloudflared.log", "a")
    try:
        proc = subprocess.Popen(
            [config.CLOUDFLARED_BINARY, "tunnel", "--url", f"http://localhost:{config.SERVER_PORT}"],
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
    except Exception:
        log_file.close()
        raise

    url = None
    start = time.time()
    while time.time() - start < config.TUNNEL_START_TIMEOUT:
        if proc.poll() is not None:
            log_file.close()
            logger.error("❌ cloudflared died during startup")
            return None, None
        try:
            with open("cloudflared.log", "r") as f:
                for line in f:
                    if "trycloudflare.com" in line:
                        match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", line)
                        if match:
                            url = match.group(0)
                            break
            if url:
                break
        except FileNotFoundError:
            pass
        time.sleep(0.5)

    log_file.flush()
    log_file.close()
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

        logger.info("\n" + "=" * 60)
        logger.info(f"🌐 PUBLIC ENDPOINT: {url}/v1")
        logger.info("=" * 60)

        while proc.poll() is None:
            time.sleep(config.TUNNEL_POLL_INTERVAL)

        logger.warning("⚠️ cloudflared DIED! Restarting in 5s...")
        time.sleep(config.TUNNEL_RESTART_DELAY)
        restart_count += 1

    logger.error("💀 Tunnel watchdog giving up")
