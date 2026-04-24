"""Animated terminal logo."""

import os
import time


def animate_logo():
    """Animated terminal logo using pyfiglet."""
    os.system("clear" if os.name != "nt" else "cls")

    import pyfiglet

    print()
    for ch in "RAGNAROK":
        art = pyfiglet.figlet_format(ch, font="slant")
        print(art)
        time.sleep(0.12)
        lines = art.count("\n")
        print("\033[F" * lines, end="\r\n" * lines)

    print()
    banner = pyfiglet.figlet_format("RAGNAROK", font="doom")
    print(banner)
    print()

    info_lines = [
        "  OpenAI-Compatible Proxy",
        "  Kaggle GPU  ->  Public API",
        "",
        "  Free LLM API for VS Code, Cursor, OpenCode, Claude Code, and more",
    ]
    for line in info_lines:
        print(line)
        time.sleep(0.08)
    print()
