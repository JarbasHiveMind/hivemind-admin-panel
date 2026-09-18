# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Every theme keeps body and muted text readable on every panel surface.

WCAG 2.x requires a contrast ratio of 4.5:1 for normal text. A theme block
sets only the tokens it changes and inherits the rest from ``:root``.

The parser reads every colour form the panel may reasonably use. A value it
cannot read fails the test instead of being dropped: a dropped value leaves
the token inheriting the ``:root`` colour, so the ratio below would be
computed for a colour that theme never shows, and an unreadable theme could
pass.
"""
import os
import re

import pytest

CSS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "hivemind_admin_panel", "static", "css", "style.css")

TEXT_TOKENS = ("--text-primary", "--text-secondary")
BG_TOKENS = ("--bg-primary", "--bg-secondary", "--bg-card", "--bg-hover")
MEASURED = TEXT_TOKENS + BG_TOKENS

_BLOCK = re.compile(r'(:root|\[data-theme="([\w-]+)"\])\s*\{([^}]*)\}')
#: every custom property declaration, whatever its value holds
_VAR = re.compile(r"(--[\w-]+):\s*([^;}]+)")
_HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_RGB = re.compile(r"rgba?\(\s*([0-9.]+)[\s,]+([0-9.]+)[\s,]+([0-9.]+)\s*"
                  r"(?:[,/]\s*([0-9.]+%?)\s*)?\)$")


class Unreadable(str):
    """A declared value this test cannot measure.

    A separate type, so a token holding one reaches the assertion instead of
    being dropped and silently inherited.
    """


def parse_color(value):
    """Return ``(r, g, b)`` for a colour this test can measure, else Unreadable.

    A translucent colour is Unreadable on purpose: its contrast depends on
    whatever is painted behind it, which this test does not model.
    """
    value = value.strip().rstrip(";").strip()
    hexed = _HEX.match(value)
    if hexed:
        digits = hexed.group(1)
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
    rgb = _RGB.match(value)
    if rgb:
        if rgb.group(4) is not None and rgb.group(4) not in ("1", "1.0", "100%"):
            return Unreadable(value)
        channels = tuple(round(float(c)) for c in rgb.groups()[:3])
        if all(0 <= c <= 255 for c in channels):
            return channels
    return Unreadable(value)


def _themes():
    with open(CSS, encoding="utf-8") as f:
        css = f.read()
    raw = {}
    for m in _BLOCK.finditer(css):
        name = m.group(2) or "dark"
        block = raw.setdefault(name, {})
        for token, value in _VAR.findall(m.group(3)):
            if token in MEASURED:
                block[token] = parse_color(value)
    base = raw["dark"]
    return {name: {**base, **tokens} for name, tokens in raw.items()}


def _luminance(rgb):
    lin = [c / 255 for c in rgb]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in lin]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_ratio_matches_known_values():
    assert contrast(parse_color("#000000"),
                    parse_color("#ffffff")) == pytest.approx(21.0)
    assert contrast(parse_color("#777777"),
                    parse_color("#ffffff")) == pytest.approx(4.48, abs=0.01)


@pytest.mark.parametrize("value,expected", [
    ("#ffffff", (255, 255, 255)),
    ("#FFF", (255, 255, 255)),
    ("#1e293b", (30, 41, 59)),
    ("#abc", (170, 187, 204)),
    ("rgb(30, 41, 59)", (30, 41, 59)),
    ("rgb(30 41 59)", (30, 41, 59)),
    ("rgba(30, 41, 59, 1)", (30, 41, 59)),
    ("rgb(30 41 59 / 100%)", (30, 41, 59)),
])
def test_the_parser_reads_the_colour_forms_the_panel_may_use(value, expected):
    assert parse_color(value) == expected


@pytest.mark.parametrize("value", [
    "rgba(30, 41, 59, 0.5)",            # translucent: the backdrop is unknown
    "rgb(30 41 59 / 50%)",
    "hsl(210, 33%, 17%)",               # a form this parser does not read
    "var(--bg-card)",                   # an unresolved reference
    "color-mix(in srgb, #fff 50%, #000)",
    "#12345",                           # not a hex length CSS accepts
    "rgb(300, 0, 0)",                   # out of range
    "inherit",
])
def test_a_colour_this_test_cannot_measure_is_marked_unreadable(value):
    assert isinstance(parse_color(value), Unreadable)


def test_all_themes_are_parsed():
    assert {"dark", "light", "darcula", "monokai", "nord", "dracula"} <= set(_themes())


@pytest.mark.parametrize("theme", sorted(_themes()))
def test_every_measured_token_is_readable(theme):
    """A token this test cannot measure fails here, rather than silently.

    Without this, an unparsed value is dropped and the token inherits the
    ``:root`` colour, so the ratio test measures a colour the theme does not
    use and can pass on a theme nobody can read.
    """
    tokens = _themes()[theme]
    bad = [f"{name}: {tokens[name]}" for name in MEASURED
           if isinstance(tokens.get(name), Unreadable)]
    missing = [name for name in MEASURED if name not in tokens]
    assert not bad, f"{theme}: this test cannot measure " + "; ".join(bad)
    assert not missing, f"{theme}: no value for " + ", ".join(missing)


@pytest.mark.parametrize("theme", sorted(_themes()))
def test_text_tokens_meet_aa_on_every_surface(theme):
    tokens = _themes()[theme]
    failures = [
        f"{fg} {tokens[fg]} on {bg} {tokens[bg]}: {contrast(tokens[fg], tokens[bg]):.2f}"
        for fg in TEXT_TOKENS for bg in BG_TOKENS
        if contrast(tokens[fg], tokens[bg]) < 4.5
    ]
    assert not failures, f"{theme}: " + "; ".join(failures)
