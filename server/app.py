"""FastAPI application for the Kaggle Ollama Proxy.

Provides an OpenAI-compatible API endpoint that proxies requests
to a local Ollama instance, handling format conversion and streaming.
"""

import time
import uuid
import asyncio
import orjson
import uvloop
import uvicorn

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager

import config
from .utils import json_loads, json_dumps, logger
from .converter import convert_messages_to_ollama
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


@app.post("/v1/chat/completions")
async def openai_compatible(request: Request):
    request_id = uuid.uuid4().hex[:8]
    logger.info(f"[{request_id}] 🔹 Request received")

    try:
        raw_body = await request.body()
        body = json_loads(raw_body)
    except (ValueError, orjson.JSONDecodeError) as e:
        logger.error(f"[{request_id}] ❌ Invalid JSON: {e}")
        error_payload = json_dumps({"error": {"message": "Invalid request body", "type": "invalid_request_error"}})
        return StreamingResponse(
            iter([b"data: " + error_payload.encode() + b"\n\n", b"data: [DONE]\n\n"]),
            media_type="text/event-stream",
        )

    model_name = body.get("model", config.MODEL_NAME)
    messages = body.get("messages", [])
    ollama_messages = convert_messages_to_ollama(messages)

    ollama_payload = {
        "model": config.OLLAMA_MODEL,
        "messages": ollama_messages,
        "stream": True,
        "think": config.THINK_ENABLED,
        "keep_alive": config.KEEP_ALIVE,
        "options": {
            "num_ctx": config.NUM_CTX,
            "num_predict": config.NUM_PREDICT,
        },
    }
    if "tools" in body and body["tools"]:
        ollama_payload["tools"] = body["tools"]
    if "tool_choice" in body:
        ollama_payload["tool_choice"] = body["tool_choice"]

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


def run_server():
    logger.info(f"🚀 Starting FastAPI on {config.SERVER_HOST}:{config.SERVER_PORT}")
    uvloop.install()
    uvicorn_config = uvicorn.Config(
        app,
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        log_level=config.UVICORN_LOG_LEVEL,
        access_log=config.UVICORN_ACCESS_LOG,
        timeout_keep_alive=config.UVICORN_TIMEOUT_KEEP_ALIVE,
        timeout_notify=config.UVICORN_TIMEOUT_NOTIFY,
        http="httptools",
        loop="uvloop",
    )
    server = uvicorn.Server(uvicorn_config)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(server.serve())
