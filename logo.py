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


def _c(text, color):
    return f"{color}{text}{_RST_}"


def animate_logo():
    """Print an animated ASCII logo."""
    os.system("clear" if os.name != "nt" else "cls")

    import pyfiglet

    banner = pyfiglet.figlet_format("RAGNAROK", font="doom")
    lines = banner.split("\n")

    print()
    for line in lines:
        for ch in line:
            if ch == " ":
                print(" ", end="", flush=True)
            else:
                print(_c(ch, _RED_), end="", flush=True)
            time.sleep(0.003)
        print()
    print()

    taglines = [
        ("  OpenAI-Compatible Proxy", _CYAN_),
        ("  Kaggle GPU  \u2192  Public API", _YELLOW_),
    ]

    for text, color in taglines:
        for ch in text:
            print(_c(ch, color), end="", flush=True)
            time.sleep(0.02)
        print()
    print()

    footer = "  Free LLM API \u2014 no key, no bill, just free GPU hours"
    for ch in footer:
        print(_c(ch, _GREEN_), end="", flush=True)
        time.sleep(0.012)
    print()
    print()