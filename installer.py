"""Installation helpers for dependencies."""

import os
import sys
import importlib
import subprocess
import shutil

import config
from progress import ProgressBar, download_with_progress


def is_installed(name):
    """Check if a system binary is available."""
    return shutil.which(name) is not None


def read_requirements():
    """Read package names from requirements.txt."""
    req_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    pkgs = []
    try:
        with open(req_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split(">")[0].split("<")[0].split("!=")[0].strip()
                    if pkg:
                        pkgs.append(pkg)
    except FileNotFoundError:
        pass
    return pkgs


def pip_packages_present():
    """Check if required Python packages are already installed."""
    for pkg in read_requirements():
        try:
            importlib.import_module(pkg)
        except ImportError:
            return False
    return True


def run_install_script():
    """Install all dependencies with progress bars (skips if already installed)."""
    print("\n  \u2500\u2500 Installing dependencies \u2500\u2500\n")

    # 1. apt-get update (only if ollama or zstd missing)
    if not is_installed("ollama") or not is_installed("zstd"):
        bar = ProgressBar("Updating apt")
        subprocess.run(["sudo", "apt-get", "update", "-qq"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        bar.done("apt updated")
    else:
        print("  \u2705 apt already up to date")

    # 2. Install zstd
    if not is_installed("zstd"):
        bar = ProgressBar("Installing zstd")
        subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "zstd"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        bar.done("zstd installed")
    else:
        print("  \u2705 zstd already installed")

    # 3. Install Ollama
    if not is_installed("ollama"):
        bar = ProgressBar("Installing Ollama")
        install_script = "/tmp/ollama-install.sh"
        try:
            subprocess.run(
                ["curl", "-fsSL", "-o", install_script, "https://ollama.com/install.sh"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            subprocess.run(
                ["bash", install_script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
        finally:
            try:
                os.remove(install_script)
            except FileNotFoundError:
                pass
        bar.done("Ollama installed")
    else:
        print("  \u2705 Ollama already installed")

    # 4. Download cloudflared (skip if binary exists and is executable)
    cf_path = config.CLOUDFLARED_BINARY
    if not (os.path.exists(cf_path) and os.access(cf_path, os.X_OK)):
        bar = ProgressBar("Downloading cloudflared")
        try:
            download_with_progress(config.CLOUDFLARED_URL, cf_path)
            os.chmod(cf_path, 0o755)
            bar.done("cloudflared downloaded")
        except Exception:
            bar.fail("cloudflared download")
    else:
        print("  \u2705 cloudflared already downloaded")

    # 5. Python packages
    if not pip_packages_present():
        bar = ProgressBar("Installing Python deps")
        req_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "-r", req_path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        bar.done("Python packages ready")
    else:
        print("  \u2705 Python packages already installed")
    print()
