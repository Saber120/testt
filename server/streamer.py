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


def make_stream_generator(ollama_base_url, model_name, ollama_payload, request_id, http_client):
    async def stream_generator():
        first_chunk = True
        has_tool_calls = False
        start_time = time.time()

        def format_error(msg, err_type="api_error"):
            err_obj = {"error": {"message": msg, "type": err_type, "param": None, "code": None}}
            return b"data: " + _dumps(err_obj) + b"\n\ndata: [DONE]\n\n"

        try:
            async with http_client.stream("POST", f"{ollama_base_url}/api/chat", json=ollama_payload) as resp:
                if resp.status_code != 200:
                    await resp.aread()
                    yield format_error(f"Ollama HTTP {resp.status_code}", "upstream_error")
                    return

                async for line in resp.aiter_lines():
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