#!/usr/bin/env python3
"""Print the `outputs:` lines for the Platane/snk action from profile.toml.

The contribution snake is the one card we do not draw ourselves, so its
colours are passed as query parameters: dots follow the activity card's ramp
and the snake is the page's rose, on both GitHub themes. The workflow runs
this and feeds the two lines to the action.
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import CONFIG, mix


def main() -> int:
    p = CONFIG.palette
    light = (p.calendar_empty, p.honey, p.amber, p.caramel, p.ink)
    # dark: a warm charcoal floor, then the same ramp climbing toward the light end
    dark_floor = mix(p.ink, "#111111", 0.55)
    dark = (
        dark_floor,
        mix(p.cocoa, dark_floor, 0.35),
        mix(p.caramel, p.cocoa, 0.3),
        p.amber,
        p.honey,
    )
    border_light = quote(p.ink + "22", safe="")
    border_dark = quote(p.cream + "22", safe="")
    snake = quote(p.rose, safe="")
    dots_l = ",".join(quote(c, safe="") for c in light)
    dots_d = ",".join(quote(c, safe="") for c in dark)
    print(
        f"dist/github-contribution-grid-snake.svg?color_snake={snake}&color_dot_border={border_light}&color_dots={dots_l}"
    )
    print(
        f"dist/github-contribution-grid-snake-dark.svg?color_snake={snake}&color_dot_border={border_dark}&color_dots={dots_d}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
