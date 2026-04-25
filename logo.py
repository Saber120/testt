"""Animated terminal logo."""

import os
import time


# ANSI color helpers
_RED_ = "\033[91m"
_CYAN_ = "\033[96m"
_YELLOW_ = "\033[93m"
_GREEN_ = "\033[92m"
_BOLD_ = "\033[1m"
_RST_ = "\033[0m"


def _colorize(text, color):
    return f"{color}{text}{_RST_}"


def animate_logo():
    """Print an animated ASCII logo with color effects."""
    os.system("clear" if os.name != "nt" else "cls")

    import pyfiglet

    banner = pyfiglet.figlet_format("RAGNAROK", font="doom")
    lines = banner.split("\n")

    # Typewriter-style reveal with color
    print()
    for line in lines:
        for ch in line:
            if ch == " ":
                print(" ", end="", flush=True)
            else:
                print(_colorize(ch, _RED_), end="", flush=True)
            time.sleep(0.005)
        print()
    print()

    time.sleep(0.3)

    tagline1 = "  OpenAI-Compatible Proxy"
    tagline2 = "  Kaggle GPU  \u2192  Public API"

    for ch in tagline1:
        print(_colorize(ch, _CYAN_), end="", flush=True)
        time.sleep(0.02)
    print()

    for ch in tagline2:
        print(_colorize(ch, _YELLOW_), end="", flush=True)
        time.sleep(0.02)
    print()
    print()

    subtitle = "  Free LLM API \u2014 no key, no bill, just free GPU hours"
    for ch in subtitle:
        print(_colorize(ch, _GREEN_), end="", flush=True)
        time.sleep(0.015)
    print()
    print()
