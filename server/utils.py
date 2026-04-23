"""Utility functions for JSON serialization and logging.

Provides fast JSON serialization via orjson when available,
falling back to the standard library json module.
"""

import logging
import json

try:
    import orjson

    def json_dumps(obj) -> str:
        """Serialize obj to a JSON string using orjson."""
        return orjson.dumps(obj).decode("utf-8")

    def json_loads(text):
        """Parse a JSON string using orjson."""
        return orjson.loads(text)

except ImportError:
    def json_dumps(obj) -> str:
        """Serialize obj to a JSON string using stdlib json."""
        return json.dumps(obj, ensure_ascii=False)

    def json_loads(text):
        """Parse a JSON string using stdlib json."""
        return json.loads(text)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ollama-proxy")
