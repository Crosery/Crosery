#!/usr/bin/env python3
"""Compile a portrait into `sprite_data.py`, a palette-indexed pixel grid.

    python3 scripts/gen-sprite.py                 # portrait named in profile.toml
    python3 scripts/gen-sprite.py <portrait.png>  # explicit file

Needs Pillow (`pip install pillow`); the card generator itself never imports
this module or the image, only the frozen `sprite_data.py` it writes.

`hero.portrait = "github"` downloads the avatar of `github.login` at 460 px.
The round token is cut where `hero.portrait_crop` says, or found by
`"auto"`: a transparent silhouette, a drawn ring on a flat background, or —
for a plain square photo — an inscribed circle.

Two things keep a likeness at 96 px: min-pooling (the darkest sample in each
block is blended over the plain average, so lash and hair lines survive the
downscale instead of smearing) and a palette of the page's own colours plus
skin, blush and iris tones sampled from the portrait, so sprite and UI are
literally the same paint.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops, ImageEnhance

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from config import CONFIG, ROOT

OUT = HERE / "sprite_data.py"
SIZE = 96
BLOCK = 8
MIN_WEIGHT = 0.42

LANCZOS = Image.Resampling.LANCZOS
BOX = Image.Resampling.BOX


# ---------------------------------------------------------------- source --


def load_portrait() -> Image.Image:
    src = CONFIG.portrait
    if src == "github":
        url = f"https://github.com/{CONFIG.login}.png?size=460"
        cache = ROOT / ".cache" / "portrait.png"
        cache.parent.mkdir(exist_ok=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "pixel-profile"})
            with urllib.request.urlopen(req, timeout=30) as r:
                cache.write_bytes(r.read())
            print(f"  downloaded {url}")
        except OSError as exc:
            if not cache.exists():
                raise SystemExit(f"could not download {url} ({exc}) and no cached copy exists") from exc
            print(f"  download failed ({exc}); using cached {cache}")
        return Image.open(cache).convert("RGBA")
    path = Path(src)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        raise SystemExit(f"hero.portrait: {path} does not exist")
    return Image.open(path).convert("RGBA")


def find_disc(im: Image.Image) -> tuple[float, float, float]:
    """(cx, cy, r) of the round token to cut from the portrait."""
    if CONFIG.portrait_crop is not None:
        return CONFIG.portrait_crop
    w, h = im.size
    alpha = im.split()[3]
    lo, _hi = alpha.getextrema()
    if int(lo) < 255:  # type: ignore[arg-type]
        mask = alpha.point(lambda v: 255 if v > 40 else 0)
        kind = "alpha"
    else:
        rgb = im.convert("RGB")
        corners = []
        for x, y in ((0, 0), (w - 6, 0), (0, h - 6), (w - 6, h - 6)):
            corners.append(
                rgb.crop((x, y, x + 6, y + 6)).resize((1, 1), BOX).getpixel((0, 0))
            )
        spread = max(max(ch) - min(ch) for ch in zip(*corners))
        if spread > 24:  # corners differ: a full-bleed photo, take the inscribed circle
            print("  portrait_crop auto: square image, inscribed circle")
            return (w / 2, h / 2, min(w, h) / 2 - 1)
        bg = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
        diff = ImageChops.difference(rgb, Image.new("RGB", (w, h), bg)).convert("L")
        mask = diff.point(lambda v: 255 if v > 28 else 0)
        kind = "flat background"
    box = mask.getbbox()
    if not box:
        return (w / 2, h / 2, min(w, h) / 2 - 1)
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0, y1 - y0
    k = max(4, int(min(bw, bh) * 0.12))
    corners_empty = all(
        mask.crop(c).getbbox() is None
        for c in (
            (x0, y0, x0 + k, y0 + k),
            (x1 - k, y0, x1, y0 + k),
            (x0, y1 - k, x0 + k, y1),
            (x1 - k, y1 - k, x1, y1),
        )
    )
    if corners_empty and abs(bw - bh) <= max(bw, bh) * 0.08:
        print(f"  portrait_crop auto: round silhouette ({kind})")
        return ((x0 + x1) / 2, (y0 + y1) / 2, min(bw, bh) / 2 * 0.975)
    print(f"  portrait_crop auto: {kind}, inscribed circle")
    return (w / 2, h / 2, min(w, h) / 2 - 1)


# --------------------------------------------------------------- palette --


def hex_rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def sample_portrait(im: Image.Image, n: int = 8) -> list[tuple[int, int, int]]:
    """The portrait's own colours, most common first — skin, hair, blush, iris.

    A median cut over the pooled 96 px image: whatever tones the face is made
    of get their own slots, so a fork's sprite keeps its skin and eye colour
    instead of being forced onto the page's six tokens.
    """
    q = im.convert("RGB").quantize(colors=n, method=Image.Quantize.MEDIANCUT).convert("RGB")
    counted = sorted(q.getcolors(1 << 16) or [], key=lambda x: -x[0])
    return [(int(c[0]), int(c[1]), int(c[2])) for _, c in counted]


def build_palette(small: Image.Image) -> list[tuple[str, tuple[int, int, int]]]:
    """Page tokens first (so outlines and highlights match the UI exactly),
    then the portrait's own tones, skipping any within a short distance of a
    colour already present."""
    pal = CONFIG.palette
    base = [
        ("milk", pal.milk),
        ("cream", pal.cream),
        ("latte", pal.latte),
        ("taupe", pal.taupe),
        ("cocoa", pal.cocoa),
        ("ink", pal.ink),
        ("amber", pal.amber),
        ("honey", pal.honey),
        ("rose", pal.rose),
        ("white", "#ffffff"),
    ]
    out = [(n, hex_rgb(h)) for n, h in base]
    for i, c in enumerate(sample_portrait(small)):
        if all(sum((a - b) ** 2 for a, b in zip(c, rgb)) > 400 for _, rgb in out):
            out.append((f"portrait{i}", c))
    return out[:16]


# ---------------------------------------------------------------- render --


def block_min(img: Image.Image, f: int) -> Image.Image:
    w, h = img.size
    out = img.crop((0, 0, w - f + 1, h - f + 1))
    for dy in range(f):
        for dx in range(f):
            if dx == 0 and dy == 0:
                continue
            out = ImageChops.darker(
                out, img.crop((dx, dy, dx + w - f + 1, dy + h - f + 1))
            )
    return out


def pooled(im: Image.Image, size: int) -> Image.Image:
    big = im.resize((size * BLOCK, size * BLOCK), LANCZOS)
    avg = big.resize((size, size), BOX)
    mn = block_min(big, BLOCK).resize((size, size), BOX)
    return Image.blend(avg, mn, MIN_WEIGHT)


def quantise(im: Image.Image, palette: list[tuple[str, tuple[int, int, int]]]) -> bytes:
    pal = Image.new("P", (1, 1))
    flat = [v for _, c in palette for v in c]
    pal.putpalette(flat + [0] * (768 - len(flat)))
    return im.quantize(palette=pal, dither=Image.Dither.NONE).tobytes()


def main() -> int:
    if len(sys.argv) > 1:
        im = Image.open(sys.argv[1]).convert("RGBA")
    else:
        im = load_portrait()
    cx, cy, r = find_disc(im)
    box = (round(cx - r), round(cy - r), round(cx + r), round(cy + r))
    # transparent pixels become the window colour so a cut-out avatar gets a plain backdrop
    backdrop = Image.new("RGBA", im.size, hex_rgb(CONFIG.palette.milk) + (255,))
    crop = Image.alpha_composite(backdrop, im).crop(box).convert("RGB")
    small = ImageEnhance.Color(pooled(crop, SIZE)).enhance(1.25)
    palette = build_palette(small)
    indices = quantise(small, palette)

    rows = []
    half = SIZE / 2
    for y in range(SIZE):
        row = []
        for x in range(SIZE):
            inside = (x + 0.5 - half) ** 2 + (y + 0.5 - half) ** 2 <= half * half
            row.append(f"{indices[y * SIZE + x]:x}" if inside else ".")
        rows.append("".join(row))

    lines = [
        f'"""Compiled pixel portrait: palette indices on a {SIZE} px grid.',
        "",
        "Generated by `scripts/gen-sprite.py` from the portrait named in profile.toml;",
        "do not edit by hand.",
        '"""',
        "",
        f"SIZE = {SIZE}",
        "",
        "PALETTE = (",
    ]
    for name, (r_, g, b) in palette:
        lines.append(f'    "#{r_:02x}{g:02x}{b:02x}",  # {name}')
    lines.append(")")
    lines.append("")
    lines.append("ROWS = (")
    for row in rows:
        lines.append(f'    "{row}",')
    lines.append(")")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    used = sorted({c for row in rows for c in row if c != "."})
    print(
        f"  wrote {OUT.name}: {SIZE}x{SIZE}, crop centre ({cx:.0f},{cy:.0f}) r {r:.0f}, {len(used)} colours used"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
