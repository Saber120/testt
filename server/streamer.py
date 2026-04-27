"""Stream Ollama responses as OpenAI-compatible Server-Sent Events."""

import uuid
import time
import asyncio

from .utils import json_loads, json_dumps, logger
from .converter import extract_text_content

try:
    import orjson
except ImportError:
    orjson = None


def _dumps(obj):
    return orjson.dumps(obj) if orjson else json_dumps(obj).encode()


def _sse_ping():
    """SSE keep-alive ping comment to prevent connection drop during idle periods."""
    return b": heartbeat\n\n"


def make_stream_generator(ollama_base_url, model_name, ollama_payload, request_id, http_client):
    async def stream_generator():
        first_chunk = True
        has_tool_calls = False
        start_time = time.time()
        ping_interval = 15

        def format_error(msg, err_type="api_error"):
            err_obj = {"error": {"message": msg, "type": err_type, "param": None, "code": None}}
            return b"data: " + _dumps(err_obj) + b"\n\ndata: [DONE]\n\n"

        def _send_ping_if_needed():
            now = time.time()
            if now - _send_ping_if_needed.last_send >= ping_interval:
                yield _sse_ping()
                _send_ping_if_needed.last_send = now

        _send_ping_if_needed.last_send = time.time()

        def _stream_reader(client, base_url, payload, queue, error_flag):
            """Background task that reads from Ollama and pushes lines to queue."""
            async def reader():
                try:
                    async with client.stream("POST", f"{base_url}/api/chat", json=payload) as resp:
                        if resp.status_code != 200:
                            await resp.aread()
                            queue.put((f"http_error:{resp.status_code}", None))
                            return

                        async for line in resp.aiter_lines():
                            queue.put(("line", line))
                        queue.put(("done", None))
                except Exception as e:
                    queue.put(("error", str(e)))
            return reader

        try:
            # Send initial ping immediately to establish the stream
            yield _sse_ping()
            _send_ping_if_needed.last_send = time.time()

            queue = asyncio.Queue(maxsize=256)
            reader_task = asyncio.create_task(_stream_reader(http_client, ollama_base_url, ollama_payload, queue, None))

            done = False
            while not done:
                # Send ping while waiting for data (handles cold start / model loading)
                ping_check = _send_ping_if_needed()
                try:
                    next(ping_check)
                except StopIteration:
                    pass

                try:
                    msg_type, payload_item = asyncio.wait_for(queue.get(), timeout=ping_interval)
                except asyncio.TimeoutError:
                    yield _sse_ping()
                    _send_ping_if_needed.last_send = time.time()
                    continue

                if msg_type == "http_error":
                    yield format_error(f"Ollama HTTP {payload_item}", "upstream_error")
                    return
                if msg_type == "error":
                    yield format_error(f"Ollama connection error: {payload_item}", "upstream_error")
                    return
                if msg_type == "done":
                    done = True
                    continue

                line = payload_item
                if not line.strip():
                    continue

                try:
                    data = json_loads(line)
                except Exception:
                    continue

                if "error" in data:
                    yield format_error(f"Ollama error: {data['error']}", "upstream_error")
                    return

                message = data.get("message", {})
                content = extract_text_content(message.get("content"))
                thinking = message.get("thinking", "")

                delta = {}
                if first_chunk:
                    delta["role"] = "assistant"
                    first_chunk = False
                    logger.info(f"[{request_id}] First token")

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
                yield b"data: " + _dumps(chunk) + b"\n\n"
                _send_ping_if_needed.last_send = time.time()

                if data.get("done"):
                    tokens = data.get("eval_count", 0)
                    elapsed = time.time() - start_time
                    logger.info(f"[{request_id}] Done | {tokens} toks | {elapsed:.1f}s")

                    final = {
                        "id": f"chatcmpl-{request_id}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [{"delta": {}, "index": 0, "finish_reason": "tool_calls" if has_tool_calls else "stop"}],
                    }
                    yield b"data: " + _dumps(final) + b"\n\n"
                    yield b"data: [DONE]\n\n"
                    return

        except Exception as e:
            logger.exception(f"[{request_id}] Error: {e}")
            yield format_error(f"Internal error: {str(e)}", "server_error")

    return stream_generator