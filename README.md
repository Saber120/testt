# Kaggle Ollama Proxy

A proxy that bridges Ollama and an OpenAI-compatible API, using a Cloudflare tunnel for public access. Designed to run on Kaggle Notebooks using free GPU resources.

## Features

- OpenAI-compatible `/v1/chat/completions` endpoint
- Streaming responses with keep-alive pings during model thinking
- Cloudflare tunnel for public URL generation
- Automatic tunnel watchdog with restart capability
- Tool calling support
- Reasoning/thinking content support

## Project Structure

```
kaggle-ollama-proxy/
├── README.md              # This file
├── config.py              # All settings in one place
├── install.sh             # Shell script for system dependencies
├── requirements.txt       # Python dependencies
├── run.py                 # Main entry point
├── server/
│   ├── __init__.py
│   ├── app.py             # FastAPI app + lifespan + routes
│   ├── converter.py       # Message conversion (OpenAI ↔ Ollama)
│   ├── streamer.py        # Streaming logic + keep-alive
│   └── utils.py           # JSON helpers + logging
├── tunnel/
│   ├── __init__.py
│   ├── cloudflare.py      # Tunnel start + watchdog + URL extraction
│   └── keepalive.py       # Keep-alive ping logic
└── kaggle_notebook.py     # Ready-to-paste Kaggle notebook cells
```

## Quick Start (Kaggle Notebook)

Copy the cells from `kaggle_notebook.py` into your Kaggle Notebook and run them in order. Make sure Internet is enabled in Kaggle settings.

## Local Development

### Prerequisites

- Python 3.9+
- Internet access

### Setup

1. Install system dependencies:
   ```bash
   bash install.sh
   ```

2. Install Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the proxy:
   ```bash
   python run.py
   ```

### Configuration

Edit `config.py` to change settings:

- `OLLAMA_BASE_URL` - Ollama API endpoint
- `OLLAMA_MODEL` - Model to use (e.g., `qwen3.6:27b`)
- `MODEL_NAME` - Exposed model name in the API
- `SERVER_PORT` - FastAPI server port
- `NUM_CTX` / `NUM_PREDICT` - Context window size
- `KEEP_ALIVE` - Model keep-alive duration

## API Usage

```bash
curl http://<tunnel-url>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nemotron-cascade-2",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "stream": true
  }'
```

## How It Works

1. Ollama runs as a background subprocess
2. FastAPI server proxies requests to Ollama's API
3. Cloudflare tunnel exposes a public HTTPS endpoint
4. Watchdog monitors tunnel health and restarts if needed
5. Keep-alive pings maintain server health during long generations

## Notes

- Ollama must run as a subprocess (not a Python library)
- Cloudflared binary is downloaded from GitHub releases (apt version is outdated)
- The asyncio wait logic in the streamer sends keep-alive pings while the model is thinking
- uvloop and httptools are used for high-performance async I/O
