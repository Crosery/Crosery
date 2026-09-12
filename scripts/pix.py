"""Pixel-art SVG toolkit for the Crosery profile.

Everything is drawn on an integer *art-pixel* grid and emitted as SVG paths,
one per colour per paint pass. `Art.svg()` sets the SVG's CSS size to twice
the grid, so one art pixel is exactly 2 CSS px in GitHub's 846 px README
column (4 device px on a 2x display). Nothing is anti-aliased and nothing sits
on a half pixel — the same discipline a game sprite sheet has.

Type is one face at one size: Fusion Pixel Font 10 px (SIL OFL 1.1), compiled
into `font_10.py`. It is proportional, mixed case and covers Chinese. Emphasis
is the bitmap-font bold — the same glyph struck twice, one pixel apart — so
headings and body are visibly the same type.

Renderer subset: GitHub proxies README images through camo and shows the SVG
inside an <img>. Only paths and SMIL <animate> are used — no <defs>,
<clipPath>, <use>, <style>, <text>, external fonts or images.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import font_10

# ------------------------------------------------------------------ palette --
# The portrait's own range — milk sweater, cream hair, amber iris, warm brown
# ink — with pixel-art rules applied: the sky and every shadow lean lavender,
# so the warm set has one cool colour to sit against and does not go flat.

MILK = "#fff7ef"  # window fill, sweater
CREAM = "#f7e8d8"  # hair light, ground
PEACH = "#f6d7c3"  # sky, low band
BLUSH = "#f2bfb8"  # cheeks, sky mid band
ROSE = "#dd8f8c"  # flowers, the snake
AMBER = "#dba85f"  # iris, stars, bars
HONEY = "#f0cf8f"  # amber light
LATTE = "#d9c2ad"  # hair shadow, tracks, hairlines
TAUPE = "#b39a89"  # decorative only (2.5:1 on milk)
COCOA = "#8a6a55"  # secondary text (4.6:1 on milk)
INK = "#4a3427"  # primary text, outlines (10.9:1 on milk)
LAVENDER = "#cfc8de"  # sky top, cool shadow
DUSK = "#a89cbf"  # lavender deep
WHITE = "#ffffff"

SKY = (LAVENDER, "#e4d0d6", BLUSH, PEACH, CREAM)  # top to bottom


# ------------------------------------------------------------------- fonts --


@dataclass(frozen=True)
class Glyph:
    adv: int
    w: int
    h: int
    xo: int
    yo: int
    rows: tuple[int, ...]  # one int per row, bit (bytes*8-1-i) = column i


_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"

Run = tuple[int, int, int, int]


class Font:
    def __init__(self, module) -> None:
        self.size: int = module.SIZE
        self.ascent: int = module.ASCENT
        self.descent: int = module.DESCENT
        self.line: int = self.ascent + self.descent
        self._table: dict[str, str] = module.GLYPHS
        self._cache: dict[str, Glyph] = {}

    def glyph(self, ch: str) -> Glyph | None:
        g = self._cache.get(ch)
        if g is not None:
            return g
        packed = self._table.get(ch)
        if packed is None:
            return None
        adv, w, h, xo, yo = (_B36.index(c) for c in packed[:5])
        digits = (w + 7) // 8 * 2
        hexrows = packed[5:]
        rows = (
            tuple(
                int(hexrows[i : i + digits], 16) for i in range(0, len(hexrows), digits)
            )
            if digits
            else ()
        )
        g = Glyph(adv, w, h, xo - 8, yo - 8, rows)
        self._cache[ch] = g
        return g

    def missing(self, s: str) -> list[str]:
        return sorted({c for c in s if c != " " and self.glyph(c) is None})

    def width(self, s: str, tracking: int = 0) -> int:
        w = 0
        for ch in s:
            g = self.glyph(ch)
            if g is not None:
                w += g.adv + tracking
        return w

    def runs(self, x: int, y: int, s: str, tracking: int = 0) -> tuple[list[Run], int]:
        """Pixel runs for `s` with its line box top-left at (x, y); returns (runs, advance)."""
        base = y + self.ascent
        out: list[Run] = []
        cx = x
        for ch in s:
            g = self.glyph(ch)
            if g is None:
                continue
            top = base - (g.yo + g.h)
            shift = (g.w + 7) // 8 * 8 - 1
            for r, bits in enumerate(g.rows):
                if not bits:
                    continue
                i = 0
                while i < g.w:
                    if bits >> (shift - i) & 1:
                        j = i
                        while j + 1 < g.w and bits >> (shift - j - 1) & 1:
                            j += 1
                        out.append((cx + g.xo + i, top + r, j - i + 1, 1))
                        i = j + 1
                    else:
                        i += 1
            cx += g.adv + tracking
        return out, cx - x

    def wrap(self, s: str, max_w: int, max_lines: int = 3) -> list[str]:
        """Greedy wrap. Latin words stay whole; CJK breaks anywhere."""
        s = " ".join((s or "").split())
        if not s:
            return []
        tokens: list[str] = []
        buf = ""
        for ch in s:
            if ch == " ":
                if buf:
                    tokens.append(buf)
                    buf = ""
                if tokens:
                    tokens[-1] += " "
                continue
            if ord(ch) > 0x2E7F:
                if buf:
                    tokens.append(buf)
                    buf = ""
                tokens.append(ch)
            else:
                buf += ch
        if buf:
            tokens.append(buf)
        lines: list[str] = []
        cur = ""
        for i, tk in enumerate(tokens):
            if not cur or self.width((cur + tk).rstrip()) <= max_w:
                cur += tk
                continue
            lines.append(cur.rstrip())
            if len(lines) == max_lines:
                lines[-1] = self.clip(
                    lines[-1] + " " + "".join(tokens[i:]).strip(), max_w
                )
                return lines
            cur = tk.lstrip()
        if cur.strip():
            lines.append(cur.rstrip())
        return lines[:max_lines]

    def clip(self, s: str, max_w: int, tracking: int = 0) -> str:
        s = " ".join((s or "").split())
        if self.width(s, tracking) <= max_w:
            return s
        out = ""
        for ch in s:
            if self.width(out + ch + "…", tracking) > max_w:
                break
            out += ch
        return out.rstrip(" ,;·-—/") + "…"


F10 = Font(font_10)


def escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ---------------------------------------------------------------- sprites --
# Small props on the same grid. '#' is the sprite's colour; other letters map
# through the `colors` legend so one shape can be recoloured.

SPARKLE_L = (
    "...#...",
    "...#...",
    "..###..",
    "#######",
    "..###..",
    "...#...",
    "...#...",
)
SPARKLE_S = (
    "..#..",
    ".###.",
    "#####",
    ".###.",
    "..#..",
)
SPARKLE_XS = (
    ".#.",
    "###",
    ".#.",
)
CURSOR = (
    "#####",
    ".###.",
    "..#..",
)
STAR = (
    "...#...",
    "..###..",
    "#######",
    ".#####.",
    "..###..",
    ".##.##.",
)
FORK = (
    "##...##",
    "##...##",
    ".#...#.",
    "..#.#..",
    "...#...",
    "..###..",
    "..###..",
)
HEART = (
    ".##.##.",
    "#######",
    "#######",
    ".#####.",
    "..###..",
    "...#...",
)
CLOUD_L = (
    "........####..........",
    "......########........",
    "...#############......",
    ".#################....",
    "######################",
    "######################",
    ".####################.",
)
CLOUD_S = (
    ".....####....",
    "...########..",
    ".############",
    "#############",
    ".###########.",
)
FLOWER = (
    ".#.",
    "#o#",
    ".#.",
    ".|.",
    ".|.",
)
TUFT = (
    "#.#.#",
    ".###.",
)


def sprite_size(rows: tuple[str, ...]) -> tuple[int, int]:
    return len(rows[0]), len(rows)


# ----------------------------------------------------------------- ledger --


@dataclass
class Box:
    name: str
    x: int
    y: int
    w: int
    h: int
    within: str | None = None


@dataclass
class Ledger:
    """Content boxes and their containers. Overlaps and spills fail the build.

    Every window registers its inner rect as a container; every piece of
    content says which container it belongs to. That is what catches a
    window border cutting through its own text — the class of bug that a
    plain overlap check on content boxes cannot see.
    """

    card: str
    boxes: list[Box] = field(default_factory=list)
    containers: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    def claim(
        self, name: str, x: int, y: int, w: int, h: int, within: str | None
    ) -> None:
        if w <= 0 or h <= 0:
            self.problems.append(f"{self.card}: {name!r} has zero size")
            return
        self.boxes.append(Box(name, x, y, w, h, within))

    def container(self, name: str, x: int, y: int, w: int, h: int) -> None:
        self.containers[name] = (x, y, w, h)

    def check(self, page_w: int, page_h: int) -> list[str]:
        for b in self.boxes:
            if b.x < 0 or b.y < 0 or b.x + b.w > page_w or b.y + b.h > page_h:
                self.problems.append(
                    f"{self.card}: {b.name!r} leaves the canvas ({b.x},{b.y} {b.w}x{b.h})"
                )
            if b.within is None:
                continue
            c = self.containers.get(b.within)
            if c is None:
                self.problems.append(
                    f"{self.card}: {b.name!r} names unknown container {b.within!r}"
                )
                continue
            cx, cy, cw, ch = c
            if b.x < cx or b.y < cy or b.x + b.w > cx + cw or b.y + b.h > cy + ch:
                self.problems.append(
                    f"{self.card}: {b.name!r} spills out of {b.within!r} "
                    f"(box {b.x},{b.y} {b.w}x{b.h}; inner {cx},{cy} {cw}x{ch})"
                )
        for i, a in enumerate(self.boxes):
            for b in self.boxes[i + 1 :]:
                ox = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
                oy = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
                if ox > 0 and oy > 0:
                    self.problems.append(
                        f"{self.card}: {a.name!r} overlaps {b.name!r} by {ox}x{oy} at ({max(a.x, b.x)},{max(a.y, b.y)})"
                    )
        return self.problems


# -------------------------------------------------------------------- art --


class Art:
    """An integer pixel canvas that emits one merged path per colour and pass.

    Within one pass, colours are painted in first-use order; `flush()` opens a
    new pass so later pixels paint over earlier ones. Helpers that overpaint
    (windows, bars, outlined text) flush for you. Animated cues are separate
    paths appended after every pass.
    """

    def __init__(self, name: str, w: int, h: int, title: str) -> None:
        self.name = name
        self.w = w
        self.h = h
        self.title = title
        self._passes: list[dict[str, list[Run]]] = [{}]
        self._under: list[str] = []  # translucent shadows, drawn before everything
        self._over: list[str] = []  # animated cues, drawn after everything
        self.led = Ledger(name)

    # ---- raw pixels ---------------------------------------------------------

    def rect(self, x: int, y: int, w: int, h: int, color: str) -> None:
        if w <= 0 or h <= 0:
            return
        self._passes[-1].setdefault(color, []).append((x, y, w, h))

    def px(self, x: int, y: int, color: str) -> None:
        self.rect(x, y, 1, 1, color)

    def flush(self) -> None:
        if self._passes[-1]:
            self._passes.append({})

    def hline(self, x: int, y: int, w: int, color: str) -> None:
        self.rect(x, y, w, 1, color)

    def vline(self, x: int, y: int, h: int, color: str) -> None:
        self.rect(x, y, 1, h, color)

    def dotted(
        self, x: int, y: int, w: int, color: str, on: int = 1, off: int = 1
    ) -> None:
        cx = x
        while cx < x + w:
            self.rect(cx, y, min(on, x + w - cx), 1, color)
            cx += on + off

    def outline(self, x: int, y: int, w: int, h: int, color: str, r: int = 1) -> None:
        """1px hollow rectangle; `r` corner pixels are skipped on each side."""
        self.hline(x + r, y, w - 2 * r, color)
        self.hline(x + r, y + h - 1, w - 2 * r, color)
        self.vline(x, y + r, h - 2 * r, color)
        self.vline(x + w - 1, y + r, h - 2 * r, color)
        if r == 2:
            for px_, py_ in (
                (x + 1, y + 1),
                (x + w - 2, y + 1),
                (x + 1, y + h - 2),
                (x + w - 2, y + h - 2),
            ):
                self.px(px_, py_, color)

    def fill_rounded(
        self, x: int, y: int, w: int, h: int, color: str, r: int = 1
    ) -> None:
        self.rect(x + r, y, w - 2 * r, h, color)
        self.rect(x, y + r, r, h - 2 * r, color)
        self.rect(x + w - r, y + r, r, h - 2 * r, color)
        if r == 2:
            self.rect(x + 1, y + 1, 1, 1, color)
            self.rect(x + w - 2, y + 1, 1, 1, color)
            self.rect(x + 1, y + h - 2, 1, 1, color)
            self.rect(x + w - 2, y + h - 2, 1, 1, color)

    def disc(self, cx: int, cy: int, r: float, color: str, r_in: float = -1.0) -> None:
        """Filled circle (or ring when `r_in` >= 0) on pixel centres."""
        lo = int(cy - r - 1)
        hi = int(cy + r + 1)
        for y in range(lo, hi + 1):
            dy = y + 0.5 - cy
            xs = [
                x
                for x in range(int(cx - r - 1), int(cx + r + 2))
                if r_in * r_in < (x + 0.5 - cx) ** 2 + dy * dy <= r * r
            ]
            if not xs:
                continue
            start = prev = xs[0]
            for x in xs[1:]:
                if x != prev + 1:
                    self.rect(start, y, prev - start + 1, 1, color)
                    start = x
                prev = x
            self.rect(start, y, prev - start + 1, 1, color)

    def dither(
        self, x: int, y: int, w: int, h: int, color: str, phase: int = 0, step: int = 1
    ) -> None:
        for yy in range(y, y + h, step):
            row = (yy - y) // step
            for xx in range(x + ((row + phase) % 2) * step, x + w, 2 * step):
                self.rect(xx, yy, min(step, x + w - xx), min(step, y + h - yy), color)

    def bands(
        self, x: int, y: int, w: int, h: int, colors: tuple[str, ...], blend: int = 4
    ) -> None:
        """Horizontal colour bands with a dithered `blend`-row seam between them."""
        n = len(colors)
        edges = [y + round(i * h / n) for i in range(n + 1)]
        for i, c in enumerate(colors):
            self.rect(x, edges[i], w, edges[i + 1] - edges[i], c)
        self.flush()
        for i in range(1, n):
            e = edges[i]
            self.dither(x, e, w, blend, colors[i - 1], phase=0, step=2)
            self.dither(x, e - blend, w, blend, colors[i], phase=1, step=2)
            self.dither(x, e + blend, w, 2, colors[i - 1], phase=1, step=1)
            self.dither(x, e - blend - 2, w, 2, colors[i], phase=0, step=1)
        self.flush()

    # ---- sprites and text ----------------------------------------------------

    def sprite(
        self,
        x: int,
        y: int,
        rows: tuple[str, ...],
        colors: dict[str, str],
        name: str | None = None,
        within: str | None = None,
    ) -> tuple[int, int]:
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                c = colors.get(ch)
                if c:
                    self.px(x + i, y + j, c)
        w, h = sprite_size(rows)
        if name:
            self.led.claim(name, x, y, w, h, within)
        return w, h

    def icon(
        self,
        x: int,
        y: int,
        rows: tuple[str, ...],
        color: str,
        name: str | None = None,
        within: str | None = None,
    ) -> tuple[int, int]:
        return self.sprite(x, y, rows, {"#": color}, name, within)

    def text(
        self,
        x: int,
        y: int,
        s: str,
        color: str,
        font: Font = F10,
        name: str | None = None,
        within: str | None = None,
        bold: bool = False,
        outline: str | None = None,
        shadow: str | None = None,
    ) -> int:
        """Set `s` with its line box top-left at (x, y); returns the advance.

        `bold` strikes every glyph twice, one pixel apart (and tracks by one
        pixel to keep the rhythm). `outline` rings the glyphs and `shadow`
        offsets a copy under them — the title-screen treatments.
        """
        gap = font.missing(s)
        if gap:
            self.led.problems.append(
                f"{self.name}: {name or s[:24]!r} needs glyphs for {gap}"
            )
            return 0
        runs, adv = font.runs(x, y, s, 1 if bold else 0)
        if bold:
            runs = runs + [(rx + 1, ry, rw, rh) for rx, ry, rw, rh in runs]
        if shadow:
            for rx, ry, rw, rh in runs:
                self.rect(rx + 1, ry + 1, rw, rh, shadow)
            self.flush()
        if outline:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx or dy:
                        for rx, ry, rw, rh in runs:
                            self.rect(rx + dx, ry + dy, rw, rh, outline)
            self.flush()
        for rx, ry, rw, rh in runs:
            self.rect(rx, ry, rw, rh, color)
        if name:
            pad = 1 if (outline or shadow) else 0
            self.led.claim(
                name, x - pad, y - pad, adv + 2 * pad, font.line + 2 * pad, within
            )
        return adv

    def text_right(
        self,
        right: int,
        y: int,
        s: str,
        color: str,
        font: Font = F10,
        name: str | None = None,
        within: str | None = None,
        bold: bool = False,
    ) -> int:
        """Right-aligned text; returns the x it starts at."""
        x = right - font.width(s, 1 if bold else 0)
        self.text(x, y, s, color, font, name, within, bold)
        return x

    def para(
        self,
        x: int,
        y: int,
        lines: list[str],
        color: str,
        font: Font = F10,
        name: str = "para",
        within: str | None = None,
        leading: int | None = None,
    ) -> int:
        """Set pre-wrapped lines; returns the y just below the last line box."""
        step = leading or font.line
        for i, ln in enumerate(lines):
            self.text(x, y + i * step, ln, color, font, f"{name}.{i}", within)
        return y + (len(lines) - 1) * step + font.line if lines else y

    def typewriter(
        self,
        x: int,
        y: int,
        s: str,
        color: str,
        font: Font,
        start: float,
        cps: float,
        period: float,
        name: str | None = None,
        within: str | None = None,
    ) -> tuple[int, float]:
        """Type `s` one glyph at a time from `start` seconds, `cps` glyphs per second.

        Each glyph is its own path with a discrete opacity step, so the text
        appears in typing order and the whole message repeats every `period`
        seconds. Renderers without SMIL show the finished text. Returns the
        advance and the time the last glyph lands.
        """
        gap = font.missing(s)
        if gap:
            self.led.problems.append(
                f"{self.name}: {name or s[:24]!r} needs glyphs for {gap}"
            )
            return 0, start
        cx = x
        t = start
        for ch in s:
            runs, adv = font.runs(cx, y, ch)
            if runs:
                d = "".join(f"M{rx} {ry}h{rw}v{rh}h-{rw}z" for rx, ry, rw, rh in runs)
                self._over.append(
                    f'<path fill="{color}" d="{d}"><animate attributeName="opacity" values="0;1" '
                    f'keyTimes="0;{t / period:.4f}" calcMode="discrete" dur="{period:.2f}s" '
                    'repeatCount="indefinite"/></path>'
                )
            cx += adv
            if ch != " ":
                t += 1.0 / cps
        if name:
            self.led.claim(name, x, y, cx - x, font.line, within)
        return cx - x, t

    # ---- windows ---------------------------------------------------------------

    def window(
        self,
        name: str,
        x: int,
        y: int,
        w: int,
        h: int,
        fill: str = MILK,
        edge: str = INK,
        inner: str | None = CREAM,
        shadow: bool = True,
        pad: int = 6,
    ) -> tuple[int, int, int, int]:
        """RPG message window: rounded 1px outline, inner highlight, offset shadow.

        Registers the inner content rect (edge + highlight + pad) as a container
        and returns it as (x, y, w, h).
        """
        if shadow:
            d = f"M{x + 3} {y + 1}h{w - 4}v1h1v1h1v{h - 4}h-1v1h-1v1h-{w - 4}v-1h-1v-1h-1v-{h - 4}h1v-1h1z"
            self._under.append(f'<path fill="{INK}" fill-opacity="0.16" d="{d}"/>')
        self.fill_rounded(x, y, w, h, fill, 2)
        self.flush()
        self.outline(x, y, w, h, edge, 2)
        if inner:
            self.outline(x + 1, y + 1, w - 2, h - 2, inner, 1)
        self.flush()
        rect = (x + 2 + pad, y + 2 + pad, w - 4 - 2 * pad, h - 4 - 2 * pad)
        self.led.container(name, *rect)
        return rect

    def tab(
        self,
        x: int,
        y: int,
        s: str,
        fill: str = INK,
        color: str = MILK,
        font: Font = F10,
        pad: int = 3,
        name: str | None = None,
        within: str | None = None,
        bold: bool = True,
    ) -> tuple[int, int]:
        """Solid label plate, e.g. the speaker name on a dialog box. Returns (w, h)."""
        w = font.width(s, 1 if bold else 0) + pad * 2 + 2
        h = font.line + 2
        self.fill_rounded(x, y, w, h, fill, 1)
        self.flush()
        self.text(x + 1 + pad, y + 1, s, color, font, bold=bold)
        if name:
            self.led.claim(name, x, y, w, h, within)
        return w, h

    def bar(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        frac: float,
        color: str,
        track: str = LATTE,
        edge: str = COCOA,
        cell: int = 2,
    ) -> None:
        """HP-style meter, filled in `cell`-wide steps so the end stays on-grid."""
        self.fill_rounded(x, y, w, h, track, 1)
        self.flush()
        steps = (w - 2) // cell
        lit = round(steps * max(0.0, min(1.0, frac)))
        if lit:
            self.rect(x + 1, y + 1, lit * cell, h - 2, color)
            self.rect(x + 1, y + 1, lit * cell, 1, mix(color, WHITE, 0.5))
        self.flush()
        self.outline(x, y, w, h, edge, 1)
        self.flush()

    # ---- animation cues (opacity only) ----------------------------------------

    def _anim_path(self, x: int, y: int, rows: tuple[str, ...]) -> str:
        return "".join(
            f"M{x + i} {y + j}h1v1h-1z"
            for j, row in enumerate(rows)
            for i, ch in enumerate(row)
            if ch == "#"
        )

    def twinkle(
        self,
        x: int,
        y: int,
        rows: tuple[str, ...],
        color: str,
        dur: float = 2.4,
        begin: float = 0.0,
    ) -> None:
        anim = (
            f'<animate attributeName="opacity" values="1;0.3;1" keyTimes="0;0.5;1" calcMode="discrete" '
            f'dur="{dur}s" begin="{begin}s" repeatCount="indefinite"/>'
        )
        self._over.append(
            f'<path fill="{color}" d="{self._anim_path(x, y, rows)}">{anim}</path>'
        )

    def cursor_blink(
        self,
        x: int,
        y: int,
        rows: tuple[str, ...],
        color: str,
        after: float,
        period: float,
        rate: float = 0.55,
    ) -> None:
        """Hidden until `after` seconds into each `period`, then blinking at `rate`."""
        times = [0.0]
        vals = ["0"]
        t = after
        on = True
        while t < period - rate / 2:
            times.append(t / period)
            vals.append("1" if on else "0")
            on = not on
            t += rate
        anim = (
            f'<animate attributeName="opacity" values="{";".join(vals)}" '
            f'keyTimes="{";".join(f"{v:.4f}" for v in times)}" calcMode="discrete" '
            f'dur="{period:.2f}s" repeatCount="indefinite"/>'
        )
        self._over.append(
            f'<path fill="{color}" d="{self._anim_path(x, y, rows)}">{anim}</path>'
        )

    # ---- output ---------------------------------------------------------------

    def svg(self, scale: int = 2) -> str:
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
            f'width="{self.w * scale}" height="{self.h * scale}" role="img" '
            f'aria-label="{escape(self.title)}" shape-rendering="crispEdges">'
        )
        parts = [head]
        parts.extend(self._under)
        for layer in self._passes:
            for color, rects in layer.items():
                d = "".join(f"M{x} {y}h{w}v{h}h-{w}z" for x, y, w, h in _merge(rects))
                parts.append(f'<path fill="{color}" d="{d}"/>')
        parts.extend(self._over)
        parts.append("</svg>")
        return "".join(parts)

    def done(self, scale: int = 2) -> tuple[str, list[str]]:
        self.led.check(self.w, self.h)
        return self.svg(scale), self.led.problems


def _merge(rects: list[Run]) -> list[Run]:
    """Merge vertically adjacent runs that share x and width."""
    by_key: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for x, y, w, h in rects:
        by_key.setdefault((x, w), []).append((y, h))
    out: list[Run] = []
    for (x, w), spans in by_key.items():
        spans.sort()
        cy, ch = spans[0]
        for y, h in spans[1:]:
            if y <= cy + ch:
                ch = max(ch, y + h - cy)
            else:
                out.append((x, cy, w, ch))
                cy, ch = y, h
        out.append((x, cy, w, ch))
    return out


def mix(a: str, b: str, t: float) -> str:
    ra, ga, ba = (int(a[i : i + 2], 16) for i in (1, 3, 5))
    rb, gb, bb = (int(b[i : i + 2], 16) for i in (1, 3, 5))
    return f"#{round(ra + (rb - ra) * t):02x}{round(ga + (gb - ga) * t):02x}{round(ba + (bb - ba) * t):02x}"


def contrast(a: str, b: str) -> float:
    def lum(h: str) -> float:
        out = []
        for i in (1, 3, 5):
            c = int(h[i : i + 2], 16) / 255
            out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]

    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)
