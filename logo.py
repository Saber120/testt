"""Animated terminal logo."""

import os
import time


_RED_ = "\033[91m"
_CYAN_ = "\033[96m"
_YELLOW_ = "\033[93m"
_GREEN_ = "\033[92m"
_GOLD_ = "\033[93m"
_RST_ = "\033[0m"


def _c(text, color):
    return f"{color}{text}{_RST_}"


def animate_logo():
    """Print an animated ASCII logo with lightning bolt."""
    os.system("clear" if os.name != "nt" else "cls")

    from art import text2art

    banner = text2art("RAGNAROK", font="basic")
    lines = banner.split("\n")

    # Pad each line to same width for clean bolt alignment
    max_len = max(len(line) for line in lines)
    padded_lines = [line.ljust(max_len) for line in lines]

    bolt = [
        "    ⚡",
        "     ╱",
        "    ╱ ",
        "     ╲",
        "      ╲",
        "     ⚡ ",
    ]

    print()
    width = max_len + len(bolt[0]) + 6
    print(_c("  ╔" + "═" * width + "╗  ", _RED_))
    print()

    for i, line in enumerate(padded_lines):
        b = bolt[i] if i < len(bolt) else "     "
        combined = f"  {line}  {b}  "
        for ch in combined:
            if ch == " ":
                print(" ", end="", flush=True)
            elif ch in ("⚡", "╱", "╲"):
                print(_c(ch, _GOLD_), end="", flush=True)
            else:
                print(_c(ch, _RED_), end="", flush=True)
            time.sleep(0.002)
        print()
    print()
    print(_c("  ╚" + "═" * width + "╝  ", _RED_))
    print()

    taglines = [
        ("  OpenAI-Compatible Proxy", _CYAN_),
        ("  Kaggle GPU  →  Public API", _YELLOW_),
    ]

    for text, color in taglines:
        for ch in text:
            print(_c(ch, color), end="", flush=True)
            time.sleep(0.02)
        print()
    print()

    footer = "  Free LLM API — no key, no bill, just free GPU hours"
    for ch in footer:
        print(_c(ch, _GREEN_), end="", flush=True)
        time.sleep(0.012)
    print()
    print()