"""Animated terminal logo."""

import os
import time


def animate_logo():
    """Print a clean ASCII logo."""
    os.system("clear" if os.name != "nt" else "cls")

    import pyfiglet

    print()
    banner = pyfiglet.figlet_format("RAGNAROK", font="doom")
    print(banner)
    print()

    print("  OpenAI-Compatible Proxy")
    print("  Kaggle GPU  ->  Public API")
    print()
    print("  Free LLM API for VS Code, Cursor, OpenCode, Claude Code, and more")
    print()
