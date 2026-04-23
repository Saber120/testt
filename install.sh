#!/bin/bash
set -e

echo "📦 Installing system dependencies..."

# Install zstd
echo "→ Installing zstd..."
sudo apt-get update -qq
sudo apt-get install -y -qq zstd

# Install Ollama
echo "→ Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh

# Download cloudflared from GitHub releases (apt version is outdated)
echo "→ Downloading cloudflared..."
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
chmod +x cloudflared

# Install Python dependencies
echo "→ Installing Python packages..."
pip install -q fastapi uvicorn httpx orjson uvloop httptools

echo "✅ Installation complete"
