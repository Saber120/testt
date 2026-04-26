"""Stream Ollama responses as OpenAI-compatible Server-Sent Events."""

import uuid
import time
import queue
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor

import httpx

from .utils import json_loads, json_dumps, logger
from .converter import extract_text_content

try:
    import orjson
except ImportError:
    orjson = None

# Shared pool for Ollama fetch threads
_fetch_pool = ThreadPoolExecutor(max_workers=50, thread_name_prefix="ollama-fetch")


def _ollama_fetch_thread(
    ollama_base_url: str,
    ollama_payload: dict,
    result_queue: queue.Queue,
    request_id: str,
    total_timeout: float,
):
    """Runs in a dedicated thread. Fetches from Ollama and puts lines in result_queue."""
    start = time.time()
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=600.0)
        ) as client:
            with client.stream("POST", f"{ollama_base_url}/api/chat", json=ollama_payload) as resp:
                if resp.status_code != 200:
                    err = resp.read().decode(errors="replace")
                    result_queue.put(("error", f"Ollama returned HTTP {resp.status_code}: {err}"))
                    return

                for line in resp.iter_lines():
                    # Thread-level total timeout
                    if time.time() - start > total_timeout:
                        result_queue.put(("timeout", "Model generation timed out"))
                        return
                    if not line.strip():
                        continue
                    result_queue.put(("line", line))

                # Normal completion
                result_queue.put(("done", None))
    except httpx.ConnectTimeout:
        result_queue.put(("error", "Ollama ConnectTimeout"))
    except httpx.ReadTimeout:
        result_queue.put(("error", "Ollama ReadTimeout"))
    except Exception as e:
        logger.exception(f"[{request_id}] Thread error: {e}")
        result_queue.put(("error", f"Ollama thread error: {str(e)}"))


def make_stream_generator(ollama_base_url, model_name, ollama_payload, request_id, http_client):
    async def stream_generator():
        first_chunk = True
        has_tool_calls = False
        start_time = time.time()

        def format_error(msg: str, err_type: str = "api_error") -> bytes:
            err_obj = {"error": {"message": msg, "type": err_type, "param": None, "code": None}}
            dumps_fn = orjson.dumps if orjson else lambda o: json_dumps(o).encode()
            return b"data: " + dumps_fn(err_obj) + b"\n\ndata: [DONE]\n\n"

        # Create a queue for the fetch thread to push lines into
        q = queue.Queue(maxsize=256)

        # Total request timeout: 10 minutes (600s)
        TOTAL_TIMEOUT = 600.0

        # Start the fetch thread
        t = threading.Thread(
            target=_ollama_fetch_thread,
            args=(ollama_base_url, ollama_payload, q, request_id, TOTAL_TIMEOUT),
            daemon=True,
        )
        t.start()

        POLL_INTERVAL = 3.0
        MAX_CONSECUTIVE_TIMEOUTS = int(TOTAL_TIMEOUT // POLL_INTERVAL) + 1
        timeout_counter = 0

        try:
            while True:
                # Poll the queue
                try:
                    msg_type, payload = q.get(timeout=POLL_INTERVAL)
                except queue.Empty:
                    timeout_counter += 1
                    if timeout_counter > MAX_CONSECUTIVE_TIMEOUTS:
                        logger.error(f"[{request_id}] Total request timeout exceeded")
                        yield format_error("Request timeout exceeded", "timeout")
                        return
                    logger.info(f"[{request_id}] Keep-alive ping (model thinking...)")
                    yield b": keep-alive\n\n"
                    continue

                if msg_type == "error":
                    logger.error(f"[{request_id}] Error: {payload}")
                    yield format_error(payload, "upstream_error")
                    return

                if msg_type == "timeout":
                    logger.error(f"[{request_id}] Timeout: {payload}")
                    yield format_error(payload, "timeout")
                    return

                if msg_type == "done":
                    elapsed = time.time() - start_time
                    logger.info(f"[{request_id}] Done | stream closed by Ollama | {elapsed:.1f}s")
                    final_chunk = {
                        "id": f"chatcmpl-{request_id}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [{"delta": {}, "index": 0, "finish_reason": "tool_calls" if has_tool_calls else "stop"}],
                    }
                    dumps_fn = orjson.dumps if orjson else lambda o: json_dumps(o).encode()
                    yield b"data: " + dumps_fn(final_chunk) + b"\n\n"
                    yield b"data: [DONE]\n\n"
                    return

                # msg_type == "line"
                line = payload
                try:
                    data = json_loads(line)
                except Exception:
                    continue

                if "error" in data:
                    logger.error(f"[{request_id}] Ollama error: {data['error']}")
                    yield format_error(f"Ollama Internal Error: {data['error']}", "upstream_error")
                    return

                message = data.get("message", {})
                content = extract_text_content(message.get("content"))
                thinking = message.get("thinking", "")

                delta = {}
                if first_chunk:
                    delta["role"] = "assistant"
                    first_chunk = False
                    logger.info(f"[{request_id}] First token received")

                if thinking:
                    delta["reasoning_content"] = thinking
                if content:
                    delta["content"] = content

                if "tool_calls" in message and message["tool_calls"]:
                    has_tool_calls = True
                    tool_calls = []
                    for idx, tc in enumerate(message["tool_calls"]):
                        func = tc.get("function", {})
                        args = func.get("arguments", {})
                        if isinstance(args, dict):
                            args = json_dumps(args)
                        tool_calls.append({
                            "index": idx,
                            "id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
                            "type": "function",
                            "function": {"name": func.get("name", ""), "arguments": args}
                        })
                    delta["tool_calls"] = tool_calls
                    if "content" in delta and not delta["content"]:
                        del delta["content"]

                if not delta:
                    continue

                chunk = {
                    "id": f"chatcmpl-{request_id}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [{"delta": delta, "index": 0, "finish_reason": None}],
                }

                dumps_fn = orjson.dumps if orjson else lambda o: json_dumps(o).encode()
                yield b"data: " + dumps_fn(chunk) + b"\n\n"

                if data.get("done"):
                    elapsed = time.time() - start_time
                    tokens_count = data.get("eval_count", 0)
                    logger.info(f"[{request_id}] Done | {tokens_count} toks | {elapsed:.1f}s")

                    final_chunk = {
                        "id": f"chatcmpl-{request_id}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [{"delta": {}, "index": 0, "finish_reason": "tool_calls" if has_tool_calls else "stop"}],
                    }
                    yield b"data: " + dumps_fn(final_chunk) + b"\n\n"
                    yield b"data: [DONE]\n\n"
                    return

        except Exception as e:
            logger.exception(f"[{request_id}] Unexpected async error: {e}")
            yield format_error(f"Internal server error: {str(e)}", "server_error")

    return stream_generator