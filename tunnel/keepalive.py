import time
import urllib.error
import urllib.request

import config
from server.utils import logger
from tunnel import cloudflare


def keep_alive_ping():
    """Periodically ping the health endpoint to keep the server alive."""
    time.sleep(config.KEEPALIVE_INITIAL_DELAY)
    while True:
        time.sleep(config.KEEPALIVE_INTERVAL)
        try:
            if cloudflare.public_url:
                urllib.request.urlopen(f"http://localhost:{config.SERVER_PORT}/health", timeout=config.KEEPALIVE_TIMEOUT)
                logger.info(f"💓 Keep-alive OK | {cloudflare.public_url}")
        except urllib.error.URLError as e:
            logger.warning(f"💓 Keep-alive failed: {e}")
        except OSError as e:
            logger.warning(f"💓 Keep-alive failed: {e}")
