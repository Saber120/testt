"""FastAPI application for the Kaggle Ollama Proxy.

Provides an OpenAI-compatible API endpoint that proxies requests
to a local Ollama instance, handling format conversion and streaming.
"""

import time
import uuid
import asyncio
import uvicorn

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from contextlib import asynccontextmanager

import config
from .utils import json_loads, json_dumps, logger
from .converter import convert_messages_to_ollama, extract_text_content
from .streamer import make_stream_generator


http_client = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    logger.info("🚀 FastAPI starting up...")
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=config.HTTP_CONNECT_TIMEOUT,
            read=config.HTTP_READ_TIMEOUT,
            write=config.HTTP_WRITE_TIMEOUT,
            pool=config.HTTP_POOL_TIMEOUT,
        ),
        limits=httpx.Limits(
            max_keepalive_connections=config.MAX_KEEPALIVE_CONNECTIONS,
            max_connections=config.MAX_CONNECTIONS,
        ),
        headers={"User-Agent": config.USER_AGENT},
    )
    yield
    logger.info("🔄 Closing http client...")
    try:
        await http_client.aclose()
    except RuntimeError:
        pass


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": int(time.time())}


@app.get("/")
async def root():
    return {"status": "ollama-proxy running", "model": config.MODEL_NAME}


@app.get("/v1")
@app.head("/v1")
async def v1_root():
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models():
    try:
        resp = await http_client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
        data = json_loads(resp.read())
    except Exception as exc:
        logger.debug(f"Failed to fetch models from Ollama: {exc}")
        data = {"models": []}

    models = []
    for m in data.get("models", []):
        models.append({
            "id": m.get("name", config.OLLAMA_MODEL),
            "object": "model",
            "created": int(time.time()),
            "owned_by": "ollama",
        })

    return JSONResponse(content={"object": "list", "data": models})


async def _get_ollama_model_name(requested_name: str) -> str:
    """Map a requested model name to an actual Ollama model, pulling if needed.

    Falls back to config.OLLAMA_MODEL if the requested model is unavailable.
    """
    if requested_name == config.OLLAMA_MODEL:
        return requested_name

    # Quick check: is the model already loaded?
    try:
        resp = await http_client.get(f"{config.OLLAMA_BASE_URL}/api/tags")
        tags = json_loads(resp.read())
        for m in tags.get("models", []):
            if m.get("name") == requested_name:
                return requested_name
    except Exception:
        pass

    # Not found — try to pull it (streaming progress)
    logger.info(f"🔻 Model '{requested_name}' not local, pulling...")
    try:
        async with http_client.stream(
            "POST",
            f"{config.OLLAMA_BASE_URL}/api/pull",
            json={"name": requested_name},
            timeout=600,
        ) as pull_resp:
            if pull_resp.status_code != 200:
                logger.warning(f"⚠️ Pull returned HTTP {pull_resp.status_code}")
                return config.OLLAMA_MODEL

            last_pct = -1
            last_status = ""
            while True:
                chunk = await pull_resp.areceive()
                if not chunk:
                    break
                try:
                    line = json_loads(chunk)
                    total = line.get("total", 0)
                    completed = line.get("completed", 0)
                    status = line.get("status", "")
                    if total and completed:
                        pct = int(completed * 100 / total)
                    else:
                        pct = -1
                    if pct != last_pct or status != last_status:
                        if pct >= 0:
                            logger.info(f"  ⬇️  {requested_name}: {status} ({pct}%)")
                        else:
                            logger.info(f"  ⬇️  {requested_name}: {status}")
                        last_pct = pct
                        last_status = status
                except Exception:
                    pass

            logger.info(f"✅ Model '{requested_name}' pulled successfully")
            return requested_name
    except Exception as exc:
        logger.warning(f"⚠️ Failed to pull '{requested_name}': {exc}")

    # Fallback
    logger.warning(f"⚠️ Falling back to default model: {config.OLLAMA_MODEL}")
    return config.OLLAMA_MODEL


@app.post("/v1/chat/completions")
async def openai_compatible(request: Request):
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[{request_id}] 🔹 Request received")

    try:
        raw_body = await request.body()
        if not raw_body:
            raise ValueError("empty request body")
        body = json_loads(raw_body)
    except ValueError as e:
        logger.error(f"[{request_id}] ❌ Invalid JSON: {e}")
        error_payload = {"error": {"message": "Invalid request body", "type": "invalid_request_error"}}
        return JSONResponse(content=error_payload, status_code=400)

    model_name = body.get("model", config.MODEL_NAME)
    messages = body.get("messages", [])
    ollama_messages = convert_messages_to_ollama(messages)
    stream = body.get("stream", True)

    # Resolve the actual Ollama model name (pull if needed, fallback otherwise)
    actual_model = await _get_ollama_model_name(model_name)

    ollama_payload = {
        "model": actual_model,
        "messages": ollama_messages,
        "stream": stream,
        "think": config.THINK_ENABLED,
        "keep_alive": config.KEEP_ALIVE,
        "options": {
            "num_ctx": config.NUM_CTX,
            "num_predict": config.NUM_PREDICT,
            "num_gpu": -1,
        },
    }
    if "tools" in body and body["tools"]:
        ollama_payload["tools"] = body["tools"]
    if "tool_choice" in body:
        ollama_payload["tool_choice"] = body["tool_choice"]

    if stream:
        ollama_payload["stream"] = True
        stream_gen = make_stream_generator(
            config.OLLAMA_BASE_URL,
            model_name,
            ollama_payload,
            request_id,
            http_client,
        )
        return StreamingResponse(
            stream_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Request-ID": request_id,
            },
        )

    ollama_payload["stream"] = False
    start_time = time.time()

    try:
        resp = await http_client.post(f"{config.OLLAMA_BASE_URL}/api/chat", json=ollama_payload)
        if resp.status_code != 200:
            logger.error(f"[{request_id}] ❌ Ollama HTTP {resp.status_code}")
            return JSONResponse(
                content={"error": {"message": f"Ollama returned HTTP {resp.status_code}", "type": "upstream_error"}},
                status_code=502,
            )

        data = json_loads(resp.read())

        if "error" in data:
            logger.error(f"[{request_id}] ❌ Ollama error: {data['error']}")
            return JSONResponse(
                content={"error": {"message": f"Ollama Internal Error: {data['error']}", "type": "upstream_error"}},
                status_code=500,
            )

        message = data.get("message", {})
        content = extract_text_content(message.get("content"))
        thinking = message.get("thinking", "")

        delta = {}
        if thinking:
            delta["reasoning_content"] = thinking
        delta["content"] = content or ""

        if "tool_calls" in message and message["tool_calls"]:
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

        elapsed = time.time() - start_time
        tokens_count = data.get("eval_count", 0)
        logger.info(f"[{request_id}] ✅ Done (non-stream) | {tokens_count} toks | {elapsed:.1f}s")

        finish_reason = "tool_calls" if delta.get("tool_calls") else "stop"

        response_body = {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_name,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": delta.get("content", ""),
                    **({"reasoning_content": delta["reasoning_content"]} if "reasoning_content" in delta else {}),
                    **({"tool_calls": delta["tool_calls"]} if "tool_calls" in delta else {}),
                },
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": tokens_count,
                "total_tokens": data.get("prompt_eval_count", 0) + tokens_count,
            },
        }

        return JSONResponse(content=response_body)

    except httpx.ReadTimeout:
        logger.error(f"[{request_id}] ❌ ReadTimeout")
        return JSONResponse(
            content={"error": {"message": "Ollama ReadTimeout", "type": "timeout"}},
            status_code=504,
        )
    except httpx.ConnectTimeout:
        logger.error(f"[{request_id}] ❌ ConnectTimeout")
        return JSONResponse(
            content={"error": {"message": "Ollama ConnectTimeout", "type": "connection_error"}},
            status_code=504,
        )
    except Exception as e:
        logger.exception(f"[{request_id}] 💥 Unexpected error: {e}")
        return JSONResponse(
            content={"error": {"message": f"Internal server error: {str(e)}", "type": "server_error"}},
            status_code=500,
        )


def run_server():
    logger.info(f"🚀 Starting FastAPI on {config.SERVER_HOST}:{config.SERVER_PORT}")

    uvloop_installed = True
    try:
        import uvloop
        uvloop.install()
    except (ImportError, RuntimeError):
        uvloop_installed = False

    httptools_installed = True
    try:
        import httptools
    except ImportError:
        httptools_installed = False

    uvicorn_kwargs = {
        "app": app,
        "host": config.SERVER_HOST,
        "port": config.SERVER_PORT,
        "log_level": config.UVICORN_LOG_LEVEL,
        "access_log": config.UVICORN_ACCESS_LOG,
        "timeout_keep_alive": config.UVICORN_TIMEOUT_KEEP_ALIVE,
        "timeout_notify": config.UVICORN_TIMEOUT_NOTIFY,
    }

    if httptools_installed:
        uvicorn_kwargs["http"] = "httptools"
    if uvloop_installed:
        uvicorn_kwargs["loop"] = "uvloop"

    uvicorn_config = uvicorn.Config(**uvicorn_kwargs)
    server = uvicorn.Server(uvicorn_config)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.serve())
