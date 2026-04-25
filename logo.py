"""Animated terminal logo."""

import os
import time
import random


_RED_ = "\033[91m"
_CYAN_ = "\033[96m"
_YELLOW_ = "\033[93m"
_GREEN_ = "\033[92m"
_WHITE_ = "\033[97m"
_BRIGHT_ = "\033[95m"
_RST_ = "\033[0m"
_CLEAR_LINE = "\033[2K\r"


def _c(text, color):
    return f"{color}{text}{_RST_}"


def _flash_line(line, color):
    """Print a single character with flash effect."""
    print(_c(line, color), end="", flush=True)


def animate_logo():
    """Print an animated ASCII logo with lightning effect."""
    os.system("clear" if os.name != "nt" else "cls")

    from art import text2art

    banner = text2art("RAGNAROK", font="basic")
    lines = banner.split("\n")

    # Pre-render the full logo in memory
    rendered = []
    for line in lines:
        row = []
        for ch in line:
            row.append(ch)
        rendered.append(row)

    print()
    print(_CLEAR_LINE)

    # Lightning strikes
    for _ in range(3):
        # Flash entire logo white briefly
        print(_CLEAR_LINE)
        for i, line in enumerate(rendered):
            row_str = "".join(line)
            print(_c(row_str, _WHITE_))
            if i < len(rendered) - 1:
                print()
        time.sleep(0.08)

        # Clear
        os.system("clear" if os.name != "nt" else "cls")
        print()
        for i, line in enumerate(rendered):
            row_str = "".join(line)
            print(row_str)
            if i < len(rendered) - 1:
                print()
        time.sleep(0.3)

    # Lightning arc effect — random columns flash
    print(_CLEAR_LINE)
    flash_count = 8
    for f in range(flash_count):
        print(_CLEAR_LINE)
        for i, line in enumerate(rendered):
            row_chars = []
            for j, ch in enumerate(line):
                if ch != " ":
                    if random.random() < 0.25:
                        row_chars.append(_c(ch, _WHITE_))
                    else:
                        row_chars.append(_c(ch, _RED_))
                else:
                    row_chars.append(ch)
            print("".join(row_chars))
            if i < len(rendered) - 1:
                print()
        time.sleep(0.06)

    # Final reveal with steady red glow
    print(_CLEAR_LINE)
    for i, line in enumerate(rendered):
        row_str = "".join(line)
        for ch in row_str:
            if ch == " ":
                print(" ", end="", flush=True)
            else:
                print(_c(ch, _RED_), end="", flush=True)
            time.sleep(0.002)
        print()
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