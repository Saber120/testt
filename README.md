# Kaggle Ollama Proxy

## 💡 Idea

Leverage **Kaggle's free GPU resources** and **Ollama's open-source models** to create a **public, OpenAI-compatible API** you can use from anywhere — your local machine, VS Code, Cursor, OpenCode, Cloud Code, or any tool that needs an LLM API.

Run a Kaggle Notebook with GPU enabled → this project installs Ollama, loads a large model onto Kaggle's Tesla T4 GPU, exposes it through a Cloudflare tunnel, and gives you a public HTTPS endpoint with full OpenAI API compatibility. No API key needed, no monthly bill — just free GPU hours.

## How It Solves The Problem

| Problem | Solution |
|---|---|
| Paid API keys (OpenAI, Anthropic, etc.) | Free Kaggle GPU + open-source models |
| Local GPU not powerful enough | Kaggle's Tesla T4 (16GB VRAM) |
| Kaggle runs in a notebook sandbox | Cloudflare tunnel exposes public HTTPS URL |
| Tools expect OpenAI format | Full `/v1/chat/completions` proxy with streaming & non-streaming |
| Notebook cell stays busy | Auto-detected Jupyter environment, releases cell after startup |

## Features

- **OpenAI-compatible API** — `/v1/chat/completions` endpoint (streaming + non-streaming)
- **`/v1/models` endpoint** — list available models on the Ollama instance
- **Streaming & non-streaming** — set `stream: false` for full response in one JSON object
- **Animated startup logo** — terminal-friendly ASCII art
- **CLI arguments** — override config without editing files
- **GPU model warm** — loads model into VRAM on startup, keeps it warm
- **Cloudflare tunnel** — public HTTPS URL with automatic watchdog restart
- **Jupyter-friendly** — detects notebook environment and releases the cell
- **Suppresses verbose output** — clean logs, no noise from apt/ollama/pip
- **Tool calling support** — OpenAI tool format converted to Ollama
- **Reasoning/thinking content** — exposed as `reasoning_content` in delta

## Project Structure

```
kaggle-ollama-proxy/
├── README.md              # This file
├── config.py              # All settings in one place
├── requirements.txt       # Python dependencies
├── run.py                 # Main entry point (setup + orchestration)
├── server/
│   ├── __init__.py
│   ├── app.py             # FastAPI app + lifespan + routes
│   ├── converter.py       # Message conversion (OpenAI ↔ Ollama)
│   ├── streamer.py        # Streaming logic + keep-alive
│   └── utils.py           # JSON helpers + logging
└── tunnel/
    ├── __init__.py
    ├── cloudflare.py      # Tunnel start + watchdog + URL extraction
    └── keepalive.py       # Keep-alive ping logic
```

## Quick Start (Kaggle Notebook)

1. Create a new Kaggle Notebook with **GPU enabled** (T4 x2) and **Internet enabled**
2. Install and run with these cells:

```python
# Cell 1: Clone and install
!git clone https://github.com/Saber120/testt.git
%cd testt
!python run.py
```

The script will:
- Install Ollama, cloudflared, and Python dependencies (all output suppressed)
- Start Ollama and pull the model
- Warm the model on GPU
- Start the FastAPI server and Cloudflare tunnel
- Print your public endpoint URL
- **Release the notebook cell** so you can continue working

## Local Development

### Prerequisites

- Python 3.9+
- Internet access

### Run

```bash
python run.py
```

That's it — `run.py` handles everything (dependencies, Ollama, tunnel).

### CLI Arguments

```bash
python run.py --help

# Override model
python run.py --models llama3.2:3b

# Custom context window
python run.py --num-ctx 32768

# Custom keep-alive
python run.py --keep-alive 120m

# Skip installation (already installed)
python run.py --skip-install

# Disable thinking mode
python run.py --no-think

# Custom port
python run.py --port 9000
```

### Configuration

Edit `config.py` to change defaults:

- `OLLAMA_MODEL` — model to use (e.g., `qwen3.6:27b`)
- `MODEL_NAME` — exposed model name in the API
- `NUM_CTX` / `NUM_PREDICT` — context window size
- `KEEP_ALIVE` — model keep-alive duration
- `THINK_ENABLED` — enable/disable reasoning mode

## API Usage

### Streaming (default)

```bash
curl https://<your-tunnel>.trycloudflare.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nemotron-cascade-2",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "stream": true
  }'
```

### Non-streaming

```bash
curl https://<your-tunnel>.trycloudflare.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nemotron-cascade-2",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "stream": false
  }'
```

### List Models

```bash
curl https://<your-tunnel>.trycloudflare.com/v1/models
```

## Connect Your Tools

Use the public tunnel URL as your OpenAI-compatible endpoint in any tool:

- **VS Code** — Continue, Cline, Copilot Custom Mode
- **Cursor** — Settings → API Provider → OpenAI-compatible
- **OpenCode** — Configure OpenAI-compatible endpoint
- **Claude Code** — Set custom API base URL
- **Any OpenAI SDK** — Set `base_url` to your tunnel URL

## How It Works

1. `run.py` installs all dependencies silently (Ollama, cloudflared, Python packages)
2. Ollama runs as a background subprocess with output suppressed
3. The model is pulled and immediately warmed into GPU memory
4. FastAPI server proxies requests, converting OpenAI ↔ Ollama formats
5. Cloudflare tunnel exposes a public HTTPS endpoint
6. Watchdog monitors tunnel health and restarts if needed (up to 20 restarts)
7. Background keep-alive thread pings `/health` every 2 minutes
8. GPU warm thread periodically queries the model to keep it loaded in VRAM
9. If running in a Jupyter notebook, the cell is released after everything starts

## Notes

- Ollama runs as a subprocess (not a Python library)
- Cloudflared binary is downloaded from GitHub releases (apt version is outdated)
- The asyncio wait logic in the streamer sends keep-alive pings while the model is thinking
- uvloop and httptools are used for high-performance async I/O
- All subprocess output is suppressed for clean notebook experience
- The script auto-detects Jupyter/Kaggle environment and releases the cell
