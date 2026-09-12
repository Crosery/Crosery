#!/usr/bin/env python3
"""Render the profile cards from `profile.toml` and live GitHub data.

    python3 scripts/gen-profile.py            # fetch + render + rewrite README.md
    python3 scripts/gen-profile.py --offline  # render from .cache/github.json

Reads GITHUB_TOKEN (or GH_TOKEN) for the GraphQL API and falls back to the `gh`
CLI, so it runs on the Actions runner and in a developer shell alike.

Pure stdlib at build time. Everything visual is frozen into committed modules:

    font_10.py        Fusion Pixel Font 10 px bitmaps (OFL 1.1)
    sprite_data.py    the portrait as a 96 px pixel grid (scripts/gen-sprite.py)
    wordmark.py       the hand-drawn pixel logotype for the title

Drawing primitives live in `pix.py`, the palette and copy in `profile.toml`
via `config.py`. Every card is authored on a 423-px art grid and emitted at
2x, so on GitHub's 846-px README column one art pixel is two CSS pixels.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pix
import sprite_data as SPRITE
import wordmark
from config import CONFIG, ROOT
from pix import F10 as F
from pix import Art

USER = CONFIG.login
ASSETS = ROOT / "assets"
CACHE = ROOT / ".cache" / "github.json"
TEMPLATE = ROOT / "README.template.md"
README = ROOT / "README.md"
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

W = 423  # art px; 846 CSS px on GitHub

# 7-px pictograms for the sign-off contacts, by the icon name used in profile.toml.
ICONS: dict[str, tuple[str, ...]] = {
    "home": (
        "...#...",
        "..###..",
        ".#####.",
        "#######",
        ".#####.",
        ".##.##.",
        ".##.##.",
    ),
    "mail": (
        "#######",
        "##...##",
        "#.#.#.#",
        "#..#..#",
        "#.....#",
        "#######",
    ),
    "github": (  # a small cat face
        "#.....#",
        "##...##",
        "#######",
        "#.###.#",
        "#######",
        ".#.#.#.",
        "..###..",
    ),
    "x": (
        "##...##",
        ".##.##.",
        "..###..",
        "..###..",
        ".##.##.",
        "##...##",
    ),
    "blog": (  # a pen nib
        ".....##",
        "....###",
        "...###.",
        "..###..",
        ".###...",
        "###....",
        "#......",
    ),
    "rss": (
        ".......",
        "###....",
        "...##..",
        "##...#.",
        "..##.#.",
        "#..#.#.",
        "##.#.#.",
    ),
    "discord": (  # a controller
        ".#####.",
        "#######",
        "##.#.##",
        "#######",
        "##...##",
        "#.....#",
        ".......",
    ),
    "telegram": (  # a paper plane
        "......#",
        "....###",
        "..#####",
        "#######",
        "..###..",
        "...##..",
        "....#..",
    ),
    "bilibili": (  # a TV
        "#.....#",
        ".#...#.",
        "#######",
        "#.....#",
        "#.#.#.#",
        "#.....#",
        "#######",
    ),
    "mastodon": (  # an elephant head
        ".#####.",
        "#######",
        "#.#.#.#",
        "#######",
        ".#####.",
        "..#.#..",
        "..#.#..",
    ),
    "linkedin": (
        "#######",
        "#.#.#.#",
        "#.#.#.#",
        "#.#.#.#",
        "#.#.#.#",
        "#.#...#",
        "#######",
    ),
}


# ---------------------------------------------------------------- fetching --

QUERY = """
query($login:String!) {
  user(login:$login) {
    name bio location createdAt
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first:100, ownerAffiliations:OWNER, isFork:false,
                 orderBy:{field:PUSHED_AT, direction:DESC}) {
      totalCount
      nodes { ...Repo }
    }
    pinnedItems(first:6, types:[REPOSITORY]) { nodes { ...Repo } }
  }
}

fragment Repo on Repository {
  name nameWithOwner description url
  stargazerCount forkCount isFork pushedAt
  owner { login }
  primaryLanguage { name color }
  languages(first:8, orderBy:{field:SIZE, direction:DESC}) {
    totalSize edges { size node { name color } }
  }
}
"""


def gql(query: str, variables: dict) -> dict:
    if TOKEN:
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": query, "variables": variables}).encode(),
            headers={
                "Authorization": f"bearer {TOKEN}",
                "Content-Type": "application/json",
                "User-Agent": "pixel-profile-generator",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read())
    else:
        args = ["gh", "api", "graphql", "-f", f"query={query}"]
        for k, v in variables.items():
            args += ["-f", f"{k}={v}"]
        payload = json.loads(subprocess.check_output(args, text=True))
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]


def printable(s: str | None) -> str:
    """Drop characters the pixel font cannot draw (emoji, joiners, selectors).

    Applied to every string that arrives from GitHub, never to the copy in
    profile.toml, where a missing glyph must fail the build instead.
    """
    if not s:
        return ""
    out = "".join(ch for ch in s if ch == " " or not F.missing(ch))
    for junk in ("\u200b", "‍", "️", "︎"):
        out = out.replace(junk, "")
    return " ".join(out.split()).strip(" /-·,;")


def fetch() -> dict:
    user = gql(QUERY, {"login": USER})["user"]
    if user is None:
        raise SystemExit(
            f"GitHub has no user named {USER!r}; check [github].login in profile.toml"
        )
    return clean(user)


def clean(data: dict) -> dict:
    """Sanitise GitHub strings and guarantee a non-empty pinned list.

    `pinnedItems` resolves against the viewer; under an Actions installation
    token that is a bot, and the list has come back empty before. That is
    treated as a degradation: fall back to the most-starred repositories and
    label the card accordingly, so a permissions surprise cannot blank the
    centrepiece.
    """
    data["bio"] = printable(data.get("bio"))
    data["location"] = printable(data.get("location"))
    for bucket in (data["repositories"]["nodes"], data["pinnedItems"]["nodes"]):
        for repo in bucket:
            if not repo:
                continue
            repo.setdefault("languages", {"totalSize": 0, "edges": []})
            repo.setdefault("owner", {"login": USER})
            repo["name"] = printable(repo.get("name"))
            repo["description"] = printable(repo.get("description"))
            lang = repo.get("primaryLanguage") or {}
            lang["name"] = printable(lang.get("name")) or None
            repo["primaryLanguage"] = lang
    if any(data["pinnedItems"]["nodes"]):
        data["_pinned_source"] = "pinned"
    else:
        print(
            "  WARNING: pinnedItems is empty; falling back to most-starred repositories."
        )
        ranked = sorted(
            data["repositories"]["nodes"], key=lambda r: -(r.get("stargazerCount") or 0)
        )
        data["pinnedItems"]["nodes"] = ranked[: CONFIG.pinned_fallback]
        data["_pinned_source"] = "stars"
    return data


# ------------------------------------------------------------------ helpers --


def fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}m"
    if n >= 10_000:
        return f"{n / 1000:.1f}k"
    return f"{n:,}"


def ago(iso: str) -> str:
    """Relative push time at day granularity.

    The cards are rebuilt once a day, so hours and minutes would be wrong for
    most of the time a card is on screen; days stay true until the next run.
    """
    try:
        when = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return ""
    days = int((datetime.now(timezone.utc) - when).total_seconds() // 86400)
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days}d ago"
    if days < 365:
        return f"{days // 30}mo ago"
    return f"{days // 365}y ago"


LANG_COLORS: dict[str, str] = {}


def collect_lang_colors(data: dict) -> None:
    for bucket in (data["repositories"]["nodes"], data["pinnedItems"]["nodes"]):
        for repo in bucket:
            for e in (repo.get("languages") or {}).get("edges") or []:
                node = e.get("node") or {}
                if node.get("name") and node.get("color"):
                    LANG_COLORS.setdefault(node["name"], node["color"])


def lang_color(repo_or_name, fallback: str = pix.TAUPE, soften: float = 0.38) -> str:
    """GitHub's own language colour, pulled toward milk so it sits in the palette."""
    if isinstance(repo_or_name, str):
        color = LANG_COLORS.get(repo_or_name)
    else:
        color = (repo_or_name.get("primaryLanguage") or {}).get("color")
    return pix.mix(color, pix.MILK, soften) if color else fallback


GEM = (
    "...#...",
    "..#o#..",
    ".#woo#.",
    "#ooooo#",
    ".#ooo#.",
    "..#o#..",
    "...#...",
)


def gem(
    a: Art,
    x: int,
    y: int,
    color: str,
    name: str | None = None,
    within: str | None = None,
) -> None:
    a.sprite(
        x,
        y,
        GEM,
        {"#": pix.INK, "o": color, "w": pix.mix(color, pix.WHITE, 0.55)},
        name,
        within,
    )


def draw_title(a: Art, x: int, y: int, max_w: int) -> tuple[int, int]:
    """The title: the pixel logotype when every letter exists, else the font at 2x.

    Both get the same treatment — ink ring, cocoa inner shadow, milk face — so
    a fork whose name has digits still lands on a title-screen logo.
    """
    rendered = wordmark.render(CONFIG.title)
    if rendered and rendered[1] <= max_w:
        cells, w, h = rendered
        rects = [(cx, cy, 1, 1) for cx, cy in cells]
    else:
        text = F.clip(CONFIG.title, max_w // 2 - 2, 1)
        runs, adv = F.runs(0, 0, text, 1)
        rects = [(rx * 2, ry * 2, rw * 2, rh * 2) for rx, ry, rw, rh in runs]
        rects += [(rx + 2, ry, rw, rh) for rx, ry, rw, rh in rects]  # bold
        w, h = adv * 2, F.line * 2
        y += (wordmark.HEIGHT - h) // 2
        h += (wordmark.HEIGHT - h) // 2  # bottom edge measured from the caller's y
    for rx, ry, rw, rh in rects:
        a.rect(x + rx - 1, y + ry - 1, rw + 2, rh + 2, pix.INK)
    a.flush()
    for rx, ry, rw, rh in rects:
        a.rect(x + rx + 1, y + ry + 1, rw, rh, pix.COCOA)
    a.flush()
    for rx, ry, rw, rh in rects:
        a.rect(x + rx, y + ry, rw, rh, pix.MILK)
    a.flush()
    a.led.claim("title", x - 1, y - 1, w + 2, h + 2, None)
    return w, h


def draw_sprite(a: Art, x: int, y: int) -> None:
    """The portrait token: the sprite inside a 1 px ink ring."""
    n = SPRITE.SIZE
    pal = SPRITE.PALETTE
    for j, row in enumerate(SPRITE.ROWS):
        for i, ch in enumerate(row):
            if ch != ".":
                a.px(x + i, y + j, pal[int(ch, 16)])
    a.flush()
    r = n / 2
    a.disc(x + n // 2, y + n // 2, r + 1.4, pix.INK, r)
    a.flush()


def pack_units(bio: str, max_w: int, max_lines: int = 2) -> list[str]:
    """Wrap a ' · '-separated bio at its separators only.

    A unit such as a kaomoji must never be split in the middle, so lines are
    packed unit by unit and an oversized unit is clipped rather than broken.
    """
    units = [u.strip() for u in bio.replace("·", " · ").split(" · ") if u.strip()]
    lines: list[str] = []
    cur = ""
    for u in units:
        cand = f"{cur} · {u}" if cur else u
        if F.width(cand) <= max_w:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        cur = F.clip(u, max_w)
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    return lines[:max_lines]


def header(
    a: Art, title: str, note: str, x: int = 10, y: int = 0, right: int = W - 12
) -> None:
    """Speaker-plate tab on the window's top edge, with a quiet note at the right."""
    a.tab(x, y, title, name="tab")
    a.text_right(right, y + 2, note, pix.COCOA, F, "note")


def ground_strip(
    a: Art, ground: int, bottom: int, tufts: tuple[int, ...], flowers: tuple[int, ...]
) -> None:
    a.rect(2, ground, W - 5, bottom - ground, pix.CREAM)
    a.hline(2, ground, W - 5, pix.LATTE)
    a.flush()
    for tx in tufts:
        a.icon(tx, ground - 2, pix.TUFT, pix.LATTE)
    for fx in flowers:
        a.sprite(
            fx, ground - 5, pix.FLOWER, {"#": pix.ROSE, "o": pix.HONEY, "|": pix.TAUPE}
        )
    a.flush()


# -------------------------------------------------------------------- cards --


def hero(d: dict) -> tuple[str, list[str]]:
    facts = list(CONFIG.facts)
    H = 170 + (14 if facts else 0)
    ground = 104 + (14 if facts else 0)
    a = Art("hero.svg", W, H, f"{USER} — pixel profile")
    a.window("hero", 0, 0, W - 1, H - 1, fill=pix.CREAM, inner=None)

    # ---- scene: sky bands, ground line, clouds, sparkles
    a.bands(2, 2, W - 5, ground - 2, pix.SKY, blend=4)
    a.flush()
    a.icon(262, 18, pix.CLOUD_S, pix.WHITE)
    a.icon(304, 6, pix.CLOUD_L, pix.WHITE)
    a.icon(380, 14, pix.CLOUD_L, pix.WHITE)
    a.twinkle(118, 24, pix.SPARKLE_S, pix.HONEY, dur=2.8)
    a.twinkle(116, 66, pix.SPARKLE_XS, pix.WHITE, dur=3.4, begin=0.9)
    a.twinkle(342, 4, pix.SPARKLE_XS, pix.HONEY, dur=2.2, begin=1.4)
    a.flush()
    ground_strip(a, ground, H - 3, (6, 112, 412), (120,))

    # ---- portrait token standing on the ground line
    sx, sy = 14, ground - SPRITE.SIZE
    for i, w in enumerate((44, 58, 62, 58, 44)):
        a.rect(sx + 48 - w // 2, ground - 2 + i, w, 1, pix.LATTE)
    a.flush()
    draw_sprite(a, sx, sy)
    a.led.claim("sprite", sx - 2, sy - 2, SPRITE.SIZE + 4, SPRITE.SIZE + 4, None)

    # ---- title block
    tx = 128
    right = W - 12
    _tw, th = draw_title(a, tx, 12, right - tx)
    bio = d.get("bio") or d.get("name") or USER
    y = a.para(tx, 12 + th + 6, pack_units(bio, right - tx), pix.INK, F, "bio", "hero") + 4
    if facts:
        a.text(
            tx, y, F.clip(" · ".join(facts), right - tx), pix.COCOA, F, "facts", "hero"
        )
        y += 14
    stars = sum(r.get("stargazerCount") or 0 for r in d["repositories"]["nodes"])
    rows = (
        (
            (fmt(d["repositories"]["totalCount"]), "repos"),
            (fmt(d["followers"]["totalCount"]), "followers"),
        ),
        (
            (fmt(stars), "stars"),
            (
                fmt(d["contributionsCollection"]["totalCommitContributions"]),
                "commits this year",
            ),
        ),
    )
    for row in rows:
        x = tx
        for i, (v, k) in enumerate(row):
            if i:
                a.px(x + 2, y + 7, pix.COCOA)
                x += 7
            x += a.text(x, y, v, pix.INK, F, f"stat.{k}", "hero", bold=True) + 3
            x += a.text(x, y, k, pix.COCOA, F, f"stat.{k}.k", "hero") + 4
        y += 14

    # ---- message window: the character speaks, one glyph at a time
    dx, dy = 10, ground + 10
    dw, dh = W - 21, H - 3 - dy - 2
    lines = CONFIG.dialog
    dh = max(dh, 10 + 14 * len(lines) + 8)
    if dy + dh > H - 5:  # a third line needs a taller card
        H = dy + dh + 5
        a.h = H
    inner = a.window(
        "dialog", dx, dy, dw, dh, fill=pix.MILK, inner=pix.CREAM, shadow=False, pad=5
    )
    a.tab(dx + 8, dy - 7, CONFIG.speaker, name="speaker")
    glyphs = sum(len(line.replace(" ", "")) for line in lines)
    period = 0.6 + glyphs / CONFIG.type_speed + 0.4 * len(lines) + CONFIG.type_hold
    t = 0.6
    for i, line in enumerate(lines):
        _, t = a.typewriter(
            inner[0] + 4,
            inner[1] + 3 + i * 14,
            F.clip(line, inner[2] - 14),
            pix.INK,
            F,
            t,
            CONFIG.type_speed,
            period,
            f"dialog.{i}",
            "dialog",
        )
        t += 0.4
    a.cursor_blink(
        inner[0] + inner[2] - 7, inner[1] + inner[3] - 4, pix.CURSOR, pix.INK, t, period
    )
    return a.done()


def pinned(d: dict) -> tuple[str, list[str]]:
    repos = [r for r in d["pinnedItems"]["nodes"] if r]
    cols = 2 if len(repos) > 1 else 1
    n_rows = (len(repos) + cols - 1) // cols
    top, pitch, cell_h = 24, 63, 58
    H = top + (n_rows - 1) * pitch + cell_h + 12
    a = Art("pinned.svg", W, H, f"{USER} — pinned projects")
    a.window("pinned", 0, 4, W - 1, H - 5, pad=4)
    source = d.get("_pinned_source", "pinned")
    header(
        a,
        "Pinned",
        f"{len(repos)} pinned · refreshed daily"
        if source == "pinned"
        else f"{len(repos)} by stars · pins unavailable",
    )

    gap = 11
    col_w = (W - 24 - gap * (cols - 1)) // cols
    for i, repo in enumerate(repos):
        r, c = divmod(i, cols)
        cx = 12 + c * (col_w + gap)
        cy = top + r * pitch
        pin_cell(a, repo, i, cx, cy, col_w)
        if c == 0 and r < n_rows - 1:
            a.dotted(12, cy + cell_h + 2, W - 24, pix.LATTE, 1, 2)
    return a.done()


def pin_cell(a: Art, repo: dict, idx: int, x: int, y: int, w: int) -> None:
    """One pinned repository: name row, two lines of description, live counts."""
    base = f"r{idx}"
    right = x + w
    gem(a, x, y + 3, lang_color(repo), f"{base}.gem", "pinned")

    upd = ago(repo.get("pushedAt") or "")
    ux = (
        a.text_right(right, y, upd, pix.COCOA, F, f"{base}.upd", "pinned")
        if upd
        else right
    )
    nx = x + 10
    nx += a.text(
        nx,
        y,
        F.clip(repo["name"], ux - 6 - nx, 1),
        pix.INK,
        F,
        f"{base}.name",
        "pinned",
        bold=True,
    )
    owner = (repo.get("owner") or {}).get("login") or USER
    if owner.lower() != USER.lower():
        handle = f"@{owner}"
        if F.width(handle) <= ux - 6 - (nx + 4):
            a.text(nx + 4, y, handle, pix.COCOA, F, f"{base}.owner", "pinned")

    desc = repo.get("description") or "No description yet."
    a.para(
        x + 10,
        y + 15,
        F.wrap(desc, w - 10, 2),
        pix.INK,
        F,
        f"{base}.desc",
        "pinned",
        leading=14,
    )

    my = y + 44
    mx = x + 10
    a.icon(mx, my + 3, pix.STAR, pix.AMBER, f"{base}.starico", "pinned")
    mx += 10
    mx += (
        a.text(
            mx,
            my,
            fmt(repo.get("stargazerCount") or 0),
            pix.INK,
            F,
            f"{base}.stars",
            "pinned",
        )
        + 8
    )
    a.icon(mx, my + 3, pix.FORK, pix.COCOA, f"{base}.forkico", "pinned")
    mx += 10
    mx += (
        a.text(
            mx,
            my,
            fmt(repo.get("forkCount") or 0),
            pix.INK,
            F,
            f"{base}.forks",
            "pinned",
        )
        + 8
    )
    lang = (repo.get("primaryLanguage") or {}).get("name") or "—"
    a.text(mx, my, F.clip(lang, right - mx), pix.COCOA, F, f"{base}.lang", "pinned")


def activity(d: dict) -> tuple[str, list[str]]:
    cal = d["contributionsCollection"]["contributionCalendar"]
    weeks = cal["weeks"]
    days = [dd for wk in weeks for dd in wk["contributionDays"]]

    cell, gap = 5, 1
    gx, gy = 34, 34
    grid_w = len(weeks) * (cell + gap) - gap
    grid_h = 7 * (cell + gap) - gap
    stats_y = gy + grid_h + 8
    rule_y = stats_y + 18
    bar_y = rule_y + 12
    by = bar_y + 14
    ly = by + 7 + 5
    H = ly + 14 + 10

    a = Art("activity.svg", W, H, f"{USER} — activity")
    a.window("activity", 0, 4, W - 1, H - 5, pad=4)
    header(
        a,
        "Activity",
        f"last 12 months · {fmt(cal['totalContributions'])} contributions",
    )

    ramp = (pix.CALENDAR_EMPTY, pix.HONEY, pix.AMBER, pix.CARAMEL, pix.COCOA, pix.INK)

    def level(n: int) -> str:
        for cap, c in ((0, 0), (1, 1), (3, 2), (7, 3), (14, 4)):
            if n <= cap:
                return ramp[c]
        return ramp[5]

    seen: set[str] = set()
    last_end = -99
    for ci, wk in enumerate(weeks):
        for ri, day in enumerate(wk["contributionDays"]):
            a.rect(
                gx + ci * (cell + gap),
                gy + ri * (cell + gap),
                cell,
                cell,
                level(day["contributionCount"]),
            )
        first = wk["contributionDays"][0]["date"] if wk["contributionDays"] else ""
        month = first[:7]
        if month and month not in seen and int(first[8:10]) <= 7:
            seen.add(month)
            label = datetime.strptime(first + "+0000", "%Y-%m-%d%z").strftime("%b")
            mx = gx + ci * (cell + gap)
            if mx > last_end + 4 and mx + F.width(label) <= gx + grid_w:
                a.text(mx, gy - 14, label, pix.COCOA, F, f"mo.{month}", "activity")
                last_end = mx + F.width(label)
    for ri, nm in ((0, "Mon"), (3, "Thu"), (6, "Sun")):
        a.text_right(
            gx - 5,
            gy + ri * (cell + gap) - 4,
            nm,
            pix.COCOA,
            F,
            f"day.{nm}",
            "activity",
        )

    cur = longest = 0
    for dd in days:
        cur = cur + 1 if dd["contributionCount"] > 0 else 0
        longest = max(longest, cur)
    streak = 0
    for dd in reversed(days):
        if dd["contributionCount"] <= 0:
            break
        streak += 1
    active = sum(1 for dd in days if dd["contributionCount"] > 0)
    a.text(
        gx,
        stats_y,
        f"{streak}-day streak · longest {longest} · active {active}/{len(days)} days",
        pix.INK,
        F,
        "streak",
        "activity",
    )
    lx = a.text_right(W - 12, stats_y, "more", pix.COCOA, F, "lg.more", "activity") - 4
    for c in reversed(ramp):
        lx -= cell + 1
        a.rect(lx, stats_y + 4, cell, cell, c)
    a.text_right(lx - 4, stats_y, "less", pix.COCOA, F, "lg.less", "activity")

    a.dotted(12, rule_y, W - 24, pix.LATTE, 1, 2)

    # language mix across public repositories: one segmented bar and a legend
    totals: dict[str, int] = {}
    for r in d["repositories"]["nodes"]:
        for e in (r.get("languages") or {}).get("edges") or []:
            name = (e.get("node") or {}).get("name") or "?"
            totals[name] = totals.get(name, 0) + (e.get("size") or 0)
    grand = sum(totals.values()) or 1
    top = sorted(totals.items(), key=lambda kv: -kv[1])[: CONFIG.stack_languages]
    a.text(12, bar_y - 1, "Stack", pix.INK, F, "stack.h", "activity", bold=True)
    a.text_right(
        W - 12,
        bar_y,
        "by bytes · public repositories",
        pix.COCOA,
        F,
        "stack.note",
        "activity",
    )
    bx, bw, bh = 12, W - 24, 7
    a.fill_rounded(bx, by, bw, bh, pix.LATTE)
    a.flush()
    x = bx + 1
    for name, size in top:
        seg = round((bw - 2) * size / grand)
        if seg > 0:
            a.rect(x, by + 1, seg, bh - 2, lang_color(name))
            x += seg
    a.flush()
    a.outline(bx, by, bw, bh, pix.COCOA)
    a.flush()
    lx = bx
    for name, size in top:  # one legend row; whatever does not fit is left to the bar
        label = f"{name} {size * 100 / grand:.0f}%"
        if lx + 7 + F.width(label) > W - 12:
            break
        a.rect(lx, ly + 4, 4, 4, lang_color(name))
        lx += 7
        lx += a.text(lx, ly, label, pix.COCOA, F, f"stack.{name}", "activity") + 10
    return a.done()


def signature(d: dict) -> tuple[str, list[str]]:
    """Sign-off: the last line of dialogue, a farewell, and contacts as a menu."""
    H = 58
    ground = 46
    a = Art("signature.svg", W, H, f"{USER} — {CONFIG.sign_off or 'contact'}")
    a.window("sign", 0, 4, W - 1, H - 5, pad=4)
    ground_strip(a, ground, 55, (10, 160, 292, 404), (118, 356))

    both = bool(CONFIG.sign_off and CONFIG.farewell)
    ty = 10 if both else 17
    if CONFIG.sign_off:
        kw = a.text(12, ty, CONFIG.sign_off, pix.INK, F, "sign_off", "sign", bold=True)
        a.twinkle(12 + kw + 5, ty + 1, pix.SPARKLE_S, pix.HONEY, dur=2.6)
        a.twinkle(12 + kw + 13, ty + 12, pix.SPARKLE_XS, pix.ROSE, dur=3.1, begin=1.1)
        ty += 15
    if CONFIG.farewell:
        a.text(12, ty, CONFIG.farewell, pix.COCOA, F, "farewell", "sign")

    # contacts: two columns of icon + label, right-aligned as a block
    contacts = list(CONFIG.contacts)
    if contacts:
        cols = [contacts[i::2] for i in range(2)] if len(contacts) > 1 else [contacts]
        col_w = [max(F.width(c.label) for c in col) + 10 for col in cols if col]
        xs: list[int] = []
        x = W - 12
        for cw in reversed(col_w):
            x -= cw
            xs.insert(0, x)
            x -= 14
        n_rows = (len(contacts) + 1) // 2
        for r in range(n_rows):
            y = (10 if n_rows > 1 else 17) + r * 15
            for c, col in enumerate(cols):
                if r >= len(col):
                    continue
                contact = col[r]
                a.icon(
                    xs[c],
                    y + 3,
                    ICONS[contact.icon],
                    pix.COCOA,
                    f"contact.{r}.{c}.icon",
                    "sign",
                )
                a.text(
                    xs[c] + 10,
                    y,
                    contact.label,
                    pix.COCOA,
                    F,
                    f"contact.{r}.{c}",
                    "sign",
                )
    return a.done()


CARDS = {
    "hero": ("hero.svg", hero, f"{USER} — pixel profile"),
    "pinned": ("pinned.svg", pinned, "Pinned projects, refreshed daily from GitHub"),
    "activity": (
        "activity.svg",
        activity,
        "Contribution calendar for the last 12 months and language mix by bytes",
    ),
    "signature": ("signature.svg", signature, "Sign-off and contacts"),
}

SNAKE = """<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/{u}/{u}/output/github-contribution-grid-snake-dark.svg" />
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/{u}/{u}/output/github-contribution-grid-snake.svg" />
  <img alt="contribution snake" src="https://raw.githubusercontent.com/{u}/{u}/output/github-contribution-grid-snake.svg" width="100%" />
</picture>"""


def write_readme() -> None:
    """Rewrite README.md from README.template.md and the configured card order."""
    if not TEMPLATE.exists():
        return
    blocks: list[str] = []
    for name in CONFIG.order:
        if name == "snake":
            blocks.append(SNAKE.format(u=USER))
            continue
        filename, _fn, alt = CARDS[name]
        img = f'<img src="./assets/{filename}" alt="{alt}" width="100%" />'
        if name == "hero":
            img = f'<a href="https://github.com/{USER}">\n  {img}\n</a>'
        blocks.append(img)
    readme = TEMPLATE.read_text(encoding="utf-8").replace(
        "{{cards}}", "\n\n".join(blocks)
    )
    if not README.exists() or README.read_text(encoding="utf-8") != readme:
        README.write_text(readme, encoding="utf-8")
        print("  README.md        rewritten")


def main() -> int:
    if "--offline" in sys.argv:
        if not CACHE.exists():
            raise SystemExit(f"--offline needs a cached response at {CACHE}")
        data = clean(json.loads(CACHE.read_text()))
    else:
        data = fetch()
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    collect_lang_colors(data)

    ASSETS.mkdir(exist_ok=True)
    problems: list[str] = []
    for name in CONFIG.order:
        if name == "snake":
            continue
        filename, fn, _alt = CARDS[name]
        svg, probs = fn(data)
        problems += probs
        (ASSETS / filename).write_text(svg, encoding="utf-8")
        print(f"  {filename:<16}{len(svg):>8} bytes")
    for name, (filename, _fn, _alt) in CARDS.items():
        if name not in CONFIG.order and (ASSETS / filename).exists():
            (ASSETS / filename).unlink()
            print(f"  {filename:<16} removed (not in cards.order)")
    write_readme()

    if problems:
        print(f"\nLAYOUT PROBLEMS ({len(problems)}):")
        for p in problems:
            print("  - " + p)
        return 1
    print("\nlayout clean: no overlaps, nothing spills, every glyph present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
