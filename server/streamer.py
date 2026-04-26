"""Stream Ollama responses as OpenAI-compatible Server-Sent Events."""

import uuid
import time
import asyncio

import httpx

from .utils import json_loads, json_dumps, logger
from .converter import extract_text_content

try:
    import orjson
except ImportError:
    orjson = None


def make_stream_generator(ollama_base_url, model_name, ollama_payload, request_id, http_client):
    async def stream_generator():
        first_chunk = True
        has_tool_calls = False
        start_time = time.time()

        def format_error(msg: str, err_type: str = "api_error") -> bytes:
            err_obj = {"error": {"message": msg, "type": err_type, "param": None, "code": None}}
            dumps_fn = orjson.dumps if orjson else lambda o: json_dumps(o).encode()
            return b"data: " + dumps_fn(err_obj) + b"\n\ndata: [DONE]\n\n"

        try:
            async with http_client.stream("POST", f"{ollama_base_url}/api/chat", json=ollama_payload) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    logger.error(f"[{request_id}] ❌ Ollama HTTP {response.status_code}")
                    yield format_error(f"Ollama returned HTTP {response.status_code}", "upstream_error")
                    return

                aiter = response.aiter_lines()
                next_item_task = asyncio.ensure_future(aiter.__anext__())
                chunk_counter = 0
                timeout_counter = 0

                while True:
                    try:
                        done, pending = await asyncio.wait({next_item_task}, timeout=15.0)

                        if not done:
                            timeout_counter += 1
                            logger.info(f"[{request_id}] 💓 Keep-alive ping #{timeout_counter} (model thinking...)")
                            yield b": keep-alive\n\n"
                            continue

                        try:
                            line = next_item_task.result()
                        except StopAsyncIteration:
                            print(f"[[DEBUG]] [{request_id}] StopAsyncIteration — stream closed by Ollama")
                            break
                        except asyncio.IncompleteReadError:
                            print(f"[[DEBUG]] [{request_id}] IncompleteReadError")
                            break
                        except Exception as e:
                            print(f"[[DEBUG]] [{request_id}] Task exception: {type(e).__name__}: {e}")
                            break

                        next_item_task = asyncio.ensure_future(aiter.__anext__())

                    except Exception as e:
                        print(f"[[DEBUG]] [{request_id}] Outer loop exception: {type(e).__name__}: {e}")
                        break

                    if not line.strip():
                        print(f"[[DEBUG]] [{request_id}] Empty line, skipping")
                        continue

                    try:
                        data = json_loads(line)
                    except Exception as e:
                        print(f"[[DEBUG]] [{request_id}] JSON parse failed: {e} | line preview: {line[:120]}")
                        continue

                    chunk_counter += 1
                    print(f"[[DEBUG]] [{request_id}] Chunk #{chunk_counter} keys: {list(data.keys())}")
                    print(f"[[DEBUG]] [{request_id}] Chunk #{chunk_counter} done={data.get('done')}, model={data.get('model','?')}")

                    if "error" in data:
                        logger.error(f"[{request_id}] ❌ Ollama error: {data['error']}")
                        yield format_error(f"Ollama Internal Error: {data['error']}", "upstream_error")
                        return

                    message = data.get("message", {})
                    print(f"[[DEBUG]] [{request_id}] message keys: {list(message.keys())}")
                    content = extract_text_content(message.get("content"))
                    thinking = message.get("thinking", "")
                    print(f"[[DEBUG]] [{request_id}] content_len={len(content)}, thinking_len={len(thinking)}")

                    delta = {}
                    if first_chunk:
                        delta["role"] = "assistant"
                        first_chunk = False
                        logger.info(f"[{request_id}] 🚀 First token received")

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

                    print(f"[[DEBUG]] [{request_id}] delta keys: {list(delta.keys())}, delta empty? {not delta}")

                    if not delta:
                        print(f"[[DEBUG]] [{request_id}] Empty delta, skipping yield")
                        continue

                    chunk = {
                        "id": f"chatcmpl-{request_id}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [{"delta": delta, "index": 0, "finish_reason": None}]
                    }

                    dumps_fn = orjson.dumps if orjson else lambda o: json_dumps(o).encode()
                    yield b"data: " + dumps_fn(chunk) + b"\n\n"
                    print(f"[[DEBUG]] [{request_id}] ✅ Yielded chunk #{chunk_counter}")

                    if data.get("done"):
                        elapsed = time.time() - start_time
                        tokens_count = data.get("eval_count", 0)
                        logger.info(f"[{request_id}] ✅ Done | {tokens_count} toks | {elapsed:.1f}s")

                        final_chunk = {
                            "id": f"chatcmpl-{request_id}",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": model_name,
                            "choices": [{"delta": {}, "index": 0, "finish_reason": "tool_calls" if has_tool_calls else "stop"}]
                        }
                        yield b"data: " + dumps_fn(final_chunk) + b"\n\n"
                        yield b"data: [DONE]\n\n"
                        print(f"[[DEBUG]] [{request_id}] 🏁 Final chunks sent, breaking")
                        break

        except httpx.ReadTimeout:
            logger.error(f"[{request_id}] ❌ ReadTimeout")
            yield format_error("Ollama ReadTimeout", "timeout")
        except httpx.ConnectTimeout:
            logger.error(f"[{request_id}] ❌ ConnectTimeout")
            yield format_error("Ollama ConnectTimeout", "connection_error")
        except Exception as e:
            logger.exception(f"[{request_id}] 💥 Unexpected error: {e}")
            yield format_error(f"Internal server error: {str(e)}", "server_error")

    return stream_generator
