#!/usr/bin/env python3
"""Compile Fusion Pixel Font BDFs into `font_<size>.py` modules.

    python3 scripts/gen-font.py fusion-pixel-12px-proportional-zh_hans.bdf \
                                fusion-pixel-10px-proportional-zh_hans.bdf \
                                fusion-pixel-8px-proportional-zh_hans.bdf

One-off. The generator (`gen-profile.py`) never touches a BDF: it imports the
frozen modules so CI needs neither the fonts nor any library.

Fusion Pixel Font is (c) TakWolf, SIL Open Font License 1.1 — see
`scripts/fonts/OFL-fusion-pixel.txt`. Only the glyphs the cards can need are
kept (Latin, Greek, Cyrillic, punctuation, symbols, kana, fullwidth forms and
the GB2312 hanzi set), which keeps each module a few hundred KB.

Record layout, one string per code point:

    "DWHXY" + hex rows          D = advance, W/H = bitmap size, X/Y = BBX offset
                                (each a single base-36 digit; X/Y stored +8)
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent

RANGES = [
    (0x0020, 0x007E),  # ASCII
    (0x00A0, 0x00FF),  # Latin-1 supplement
    (0x0100, 0x017F),  # Latin extended-A
    (0x0370, 0x03FF),  # Greek (the kaomoji's omega)
    (0x0400, 0x045F),  # Cyrillic
    (0x2000, 0x206F),  # general punctuation (— … ‘ ’ “ ”)
    (0x20A0, 0x20CF),  # currency
    (0x2100, 0x214F),  # letterlike
    (0x2190, 0x21FF),  # arrows
    (0x2200, 0x22FF),  # math operators
    (0x2300, 0x23FF),  # misc technical (⌒)
    (0x2460, 0x24FF),  # enclosed alphanumerics
    (0x2500, 0x257F),  # box drawing
    (0x2580, 0x259F),  # block elements
    (0x25A0, 0x25FF),  # geometric shapes (▲ ▼ ◆ ●)
    (0x2600, 0x26FF),  # misc symbols (★ ☆ ♪)
    (0x2700, 0x27BF),  # dingbats
    (0x3000, 0x303F),  # CJK symbols and punctuation
    (0x3040, 0x309F),  # hiragana
    (0x30A0, 0x30FF),  # katakana
    (0xFF00, 0xFFEF),  # fullwidth forms
]


@dataclass
class Glyph:
    enc: int = -1
    dw: int = 0
    bbx: tuple[int, int, int, int] = (0, 0, 0, 0)
    rows: list[str] = field(default_factory=list)


def parse_bdf(path: Path) -> tuple[dict[int, Glyph], dict[str, int]]:
    glyphs: dict[int, Glyph] = {}
    props: dict[str, int] = {}
    cur = Glyph()
    with path.open(encoding="utf-8", errors="replace") as f:
        it = iter(f)
        for line in it:
            if line.startswith(("FONT_ASCENT", "FONT_DESCENT", "PIXEL_SIZE")):
                key, val = line.split()[:2]
                props[key] = int(val)
            elif line.startswith("STARTCHAR"):
                cur = Glyph()
            elif line.startswith("ENCODING"):
                cur.enc = int(line.split()[1])
            elif line.startswith("DWIDTH"):
                cur.dw = int(line.split()[1])
            elif line.startswith("BBX"):
                w, h, xo, yo = (int(v) for v in line.split()[1:5])
                cur.bbx = (w, h, xo, yo)
            elif line.startswith("BITMAP"):
                for row in it:
                    if row.startswith("ENDCHAR"):
                        break
                    cur.rows.append(row.strip())
                if cur.enc >= 0:
                    glyphs[cur.enc] = cur
    return glyphs, props


def wanted(cp: int) -> bool:
    for lo, hi in RANGES:
        if lo <= cp <= hi:
            return True
    if 0x4E00 <= cp <= 0x9FFF:
        try:
            chr(cp).encode("gb2312")
            return True
        except UnicodeEncodeError:
            return False
    return False


def b36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if not 0 <= n < 36:
        raise ValueError(f"out of base-36 range: {n!r}")
    return digits[n]


def pack(dw: int, w: int, h: int, xo: int, yo: int, hexrows: list[str]) -> str:
    return b36(dw) + b36(w) + b36(h) + b36(xo + 8) + b36(yo + 8) + "".join(hexrows)


def rows_to_hex(rows: list[str]) -> list[str]:
    out = []
    for r in rows:
        bits = "".join("1" if c == "#" else "0" for c in r)
        bits += "0" * (-len(bits) % 8)
        out.append(f"{int(bits, 2):0{len(bits) // 4}X}")
    return out


# The 8 px face lacks a couple of the kaomoji's characters; drawn here on its
# grid so `ciallo～[∠・ω< ]⌒★` survives at reading size.
SMALL_EXTRAS: dict[int, dict[str, tuple[tuple[int, int, int], list[str]]]] = {
    8: {
        "ω": ((6, 0, 0), ["#...#", "#.#.#", "#.#.#", ".#.#."]),
        "⌒": ((8, 0, 5), [".#####.", "#.....#"]),
    },
}


def angle_glyph(size: int) -> tuple[tuple[int, int, int], list[str]]:
    """'∠' — the font lacks it and the ciallo kaomoji needs it.

    A diagonal from top-right to bottom-left closed by a base line, drawn on
    the hanzi box of the given size so it sits beside '・ω<' at full width.
    """
    n = size - 1
    rows = ["." * (n - 1 - i) + "#" + "." * i for i in range(n - 1)]
    rows.append("#" * n)
    return (size, 0, -1), rows


def compile_font(src: Path) -> Path:
    glyphs, props = parse_bdf(src)
    size = props["PIXEL_SIZE"]
    ascent, descent = props["FONT_ASCENT"], props["FONT_DESCENT"]

    table: dict[str, str] = {}
    for cp, g in glyphs.items():
        if not wanted(cp):
            continue
        w, h, xo, yo = g.bbx
        if g.rows and any(len(r) * 4 < w for r in g.rows):
            raise SystemExit(f"row too short for U+{cp:04X}")
        table[chr(cp)] = pack(g.dw, w, h, xo, yo, g.rows)

    # Fill-ins for glyphs a given size lacks; a size that ships its own wins.
    extras = {"∠": angle_glyph(size), **SMALL_EXTRAS.get(size, {})}
    for ch, ((dw, xo, yo), rows) in extras.items():
        if ch in table:
            continue
        w = max(len(r) for r in rows)
        table[ch] = pack(dw, w, len(rows), xo, yo, rows_to_hex(rows))

    out = HERE / f"font_{size}.py"
    lines = [
        f'"""Fusion Pixel Font {size}px (proportional, zh_hans), compiled bitmaps.',
        "",
        "Generated by `scripts/gen-font.py`; do not edit by hand.",
        "",
        "Fusion Pixel Font (c) 2022 TakWolf, https://github.com/TakWolf/fusion-pixel-font",
        "Licensed under the SIL Open Font License, Version 1.1:",
        "scripts/fonts/OFL-fusion-pixel.txt",
        "",
        "Each value packs advance, bitmap width, height, x/y offset (+8) as base-36",
        "digits, then the bitmap rows as hex, MSB first, one row per ceil(w/8) bytes.",
        '"""',
        "",
        f"SIZE = {size}",
        f"ASCENT = {ascent}",
        f"DESCENT = {descent}",
        "",
        "GLYPHS = {",
    ]
    for ch in sorted(table):
        lines.append(f"    {ch!r}: {table[ch]!r},")
    lines.append("}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out.name}: {len(table)} glyphs, {out.stat().st_size // 1024} KB")
    return out


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for arg in sys.argv[1:]:
        compile_font(Path(arg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
