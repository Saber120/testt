"""Configuration for the Kaggle Ollama Proxy.

All magic numbers and settings are externalized here for easy customization.
"""

# Ollama server settings
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3.6:27b"
MODEL_NAME = "nemotron-cascade-2"

# Server settings
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000

# Ollama request options
NUM_CTX = 62768
NUM_PREDICT = 62768
KEEP_ALIVE = "60m"

# Think mode
THINK_ENABLED = True

# HTTP client timeouts
HTTP_CONNECT_TIMEOUT = 60.0
HTTP_READ_TIMEOUT = 900.0
HTTP_WRITE_TIMEOUT = 60.0
HTTP_POOL_TIMEOUT = 900.0

# Connection limits
MAX_KEEPALIVE_CONNECTIONS = 500
MAX_CONNECTIONS = 2000

# Tunnel settings
TUNNEL_START_TIMEOUT = 60
TUNNEL_MAX_RESTARTS = 20
TUNNEL_POLL_INTERVAL = 5
TUNNEL_RESTART_DELAY = 5
CLOUDFLARED_BINARY = "./cloudflared"

# Keep-alive settings
KEEPALIVE_INITIAL_DELAY = 30
KEEPALIVE_INTERVAL = 120
KEEPALIVE_TIMEOUT = 10

# Uvicorn server settings
UVICORN_LOG_LEVEL = "warning"
UVICORN_ACCESS_LOG = False
UVICORN_TIMEOUT_KEEP_ALIVE = 300
UVICORN_TIMEOUT_NOTIFY = 60

# Cloudflare download URL
CLOUDFLARED_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"

# User agent
USER_AGENT = "ollama-proxy/1.0"
