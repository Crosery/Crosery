"""Load and validate `profile.toml`.

Pure stdlib (tomllib, Python 3.11+). Every consumer imports `CONFIG` from
here so a typo in the TOML fails once, early, with the key path in the
message rather than as a KeyError deep inside a card.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "profile.toml"

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
CARD_NAMES = ("hero", "pinned", "activity", "snake", "signature")
ICON_NAMES = (
    "home",
    "mail",
    "github",
    "x",
    "blog",
    "rss",
    "discord",
    "telegram",
    "bilibili",
    "mastodon",
    "linkedin",
)


class ConfigError(SystemExit):
    def __init__(self, path: str, why: str) -> None:
        super().__init__(f"profile.toml: [{path}] {why}")


@dataclass(frozen=True)
class Contact:
    icon: str
    label: str


@dataclass(frozen=True)
class Palette:
    milk: str
    cream: str
    ink: str
    cocoa: str
    amber: str
    rose: str
    sky: tuple[str, ...]
    honey: str
    latte: str
    taupe: str
    caramel: str
    calendar_empty: str


@dataclass(frozen=True)
class Config:
    login: str
    title: str
    portrait: str
    portrait_crop: tuple[int, int, int] | None  # None means auto
    facts: tuple[str, ...]
    speaker: str
    dialog: tuple[str, ...]
    type_speed: float
    type_hold: float
    sign_off: str
    farewell: str
    contacts: tuple[Contact, ...]
    palette: Palette
    order: tuple[str, ...]
    pinned_fallback: int
    stack_languages: int
    raw: dict = field(repr=False, compare=False)


# ------------------------------------------------------------------ colour --


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
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


# ----------------------------------------------------------------- reading --


def _lookup(table: dict, path: str):
    node = table
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _str(table: dict, path: str, default: str) -> str:
    node = _lookup(table, path)
    if node is None:
        return default
    if not isinstance(node, str):
        raise ConfigError(path, f"must be a string, got {type(node).__name__}")
    return node.strip()


def _num(table: dict, path: str, default: float) -> float:
    node = _lookup(table, path)
    if node is None:
        return default
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        raise ConfigError(path, f"must be a number, got {type(node).__name__}")
    return float(node)


def _int(table: dict, path: str, default: int) -> int:
    node = _lookup(table, path)
    if node is None:
        return default
    if isinstance(node, bool) or not isinstance(node, int):
        raise ConfigError(path, f"must be an integer, got {type(node).__name__}")
    return node


def _str_list(table: dict, path: str) -> tuple[str, ...]:
    node = _lookup(table, path)
    if node is None:
        return ()
    if not isinstance(node, list):
        raise ConfigError(path, "must be a list")
    for i, item in enumerate(node):
        if not isinstance(item, str):
            raise ConfigError(f"{path}[{i}]", "must be a string")
    return tuple(item.strip() for item in node)


def _color(table: dict, path: str, default: str) -> str:
    value = _str(table, path, default)
    if not _HEX.match(value):
        raise ConfigError(path, f"must be a #rrggbb colour, got {value!r}")
    return value.lower()


def load(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        raise SystemExit(
            f"{path} not found — copy profile.toml from the template repository"
        )
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    login = _str(raw, "github.login", "")
    if not _LOGIN.match(login):
        raise ConfigError("github.login", f"{login!r} is not a GitHub login")

    title = _str(raw, "hero.title", login) or login
    portrait = _str(raw, "hero.portrait", "github") or "github"
    crop_node = _lookup(raw, "hero.portrait_crop")
    portrait_crop: tuple[int, int, int] | None
    if crop_node is None or crop_node == "auto":
        portrait_crop = None
    elif (
        isinstance(crop_node, list)
        and len(crop_node) == 3
        and all(
            isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in crop_node
        )
    ):
        portrait_crop = (crop_node[0], crop_node[1], crop_node[2])
    else:
        raise ConfigError(
            "hero.portrait_crop", 'must be "auto" or [centre_x, centre_y, radius]'
        )
    facts = tuple(f for f in _str_list(raw, "hero.facts") if f)

    speaker = _str(raw, "dialog.speaker", login) or login
    dialog = tuple(line for line in _str_list(raw, "dialog.lines") if line)
    if not 1 <= len(dialog) <= 3:
        raise ConfigError(
            "dialog.lines", f"needs 1 to 3 non-empty lines, got {len(dialog)}"
        )
    type_speed = _num(raw, "dialog.speed", 26.0)
    type_hold = _num(raw, "dialog.hold", 12.0)
    if type_speed <= 0 or type_hold < 0:
        raise ConfigError("dialog", "speed must be > 0 and hold >= 0")

    sign_off = _str(raw, "signature.sign_off", "")
    farewell = _str(raw, "signature.farewell", "")
    entries = _lookup(raw, "signature.contacts")
    contacts: list[Contact] = []
    for i, entry in enumerate(entries or []):
        if not isinstance(entry, dict):
            raise ConfigError(
                f"signature.contacts[{i}]", "must be a table with icon and label"
            )
        icon = str(entry.get("icon", "")).strip().lower()
        label = str(entry.get("label", "")).strip()
        if icon not in ICON_NAMES:
            raise ConfigError(
                f"signature.contacts[{i}].icon",
                f"{icon!r} is not one of {', '.join(ICON_NAMES)}",
            )
        if not label:
            raise ConfigError(f"signature.contacts[{i}].label", "is empty")
        contacts.append(Contact(icon, label))
    if len(contacts) > 6:
        raise ConfigError("signature.contacts", "at most 6 contacts fit the card")

    milk = _color(raw, "palette.milk", "#fff7ef")
    cream = _color(raw, "palette.cream", "#f7e8d8")
    ink = _color(raw, "palette.ink", "#4a3427")
    cocoa = _color(raw, "palette.cocoa", "#8a6a55")
    amber = _color(raw, "palette.amber", "#dba85f")
    rose = _color(raw, "palette.rose", "#dd8f8c")
    sky = _str_list(raw, "palette.sky") or (
        "#cfc8de",
        "#e4d0d6",
        "#f2bfb8",
        "#f6d7c3",
        cream,
    )
    for i, c in enumerate(sky):
        if not _HEX.match(c):
            raise ConfigError(
                f"palette.sky[{i}]", f"must be a #rrggbb colour, got {c!r}"
            )
    if len(sky) < 2:
        raise ConfigError("palette.sky", "needs at least two colours")
    latte = _color(raw, "palette.latte", mix(cream, ink, 0.18))
    palette = Palette(
        milk=milk,
        cream=cream,
        ink=ink,
        cocoa=cocoa,
        amber=amber,
        rose=rose,
        sky=tuple(c.lower() for c in sky),
        honey=_color(raw, "palette.honey", mix(amber, milk, 0.45)),
        latte=latte,
        taupe=_color(raw, "palette.taupe", mix(cream, ink, 0.4)),
        caramel=_color(raw, "palette.caramel", mix(amber, ink, 0.25)),
        calendar_empty=_color(raw, "palette.calendar_empty", mix(cream, latte, 0.2)),
    )
    if contrast(ink, milk) < 4.5:
        raise ConfigError(
            "palette",
            f"ink on milk is {contrast(ink, milk):.1f}:1; text needs at least 4.5:1",
        )
    if contrast(cocoa, milk) < 3.0:
        raise ConfigError(
            "palette",
            f"cocoa on milk is {contrast(cocoa, milk):.1f}:1; captions need at least 3:1",
        )

    order = _str_list(raw, "cards.order") or CARD_NAMES
    for i, name in enumerate(order):
        if name not in CARD_NAMES:
            raise ConfigError(
                f"cards.order[{i}]", f"{name!r} is not one of {', '.join(CARD_NAMES)}"
            )
    if len(set(order)) != len(order):
        raise ConfigError("cards.order", "lists a card twice")
    pinned_fallback = _int(raw, "cards.pinned_fallback", 6)
    stack_languages = _int(raw, "cards.stack_languages", 6)
    if not 1 <= pinned_fallback <= 6:
        raise ConfigError("cards.pinned_fallback", "must be 1–6")
    if not 1 <= stack_languages <= 8:
        raise ConfigError("cards.stack_languages", "must be 1–8")

    return Config(
        login=login,
        title=title,
        portrait=portrait,
        portrait_crop=portrait_crop,
        facts=facts,
        speaker=speaker,
        dialog=dialog,
        type_speed=type_speed,
        type_hold=type_hold,
        sign_off=sign_off,
        farewell=farewell,
        contacts=tuple(contacts),
        palette=palette,
        order=tuple(order),
        pinned_fallback=pinned_fallback,
        stack_languages=stack_languages,
        raw=raw,
    )


CONFIG = load()
