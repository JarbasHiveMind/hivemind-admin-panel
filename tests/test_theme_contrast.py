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


# ------------------------------------------------------------------ accents
#
# An accent has two roles. As text it needs 4.5:1 on every surface. As a
# button fill or a border it is a non-text element and needs 3:1 against the
# surface it sits on (WCAG 1.4.11). One colour can not do both in every theme,
# so each accent has a fill token ``--accent-<name>`` and a text token
# ``--accent-<name>-text``.

ACCENTS = ("primary", "secondary", "danger", "warning", "success")
ACCENT_TEXT = tuple(f"--accent-{a}-text" for a in ACCENTS)
ACCENT_FILL = tuple(f"--accent-{a}" for a in ACCENTS)
FILL_SURFACES = ("--bg-primary", "--bg-card")
MEASURED = MEASURED + ACCENT_TEXT + ACCENT_FILL + ("--on-danger",)

#: (fill token, text colour) for each button that paints text on an accent.
#: A string starting with ``--`` is a token, anything else a literal colour.
BUTTON_TEXT = {
    "btn-primary/primary": ("--accent-primary", "--bg-primary"),
    "btn-primary/secondary": ("--accent-secondary", "--bg-primary"),
    "btn-danger": ("--accent-danger", "--on-danger"),
    "btn-success": ("--accent-success", "--bg-primary"),
    "btn-warning": ("--accent-warning", "#1e1e1e"),
}

#: Button text ratios before the accent tokens were split. A button that met
#: 4.5:1 must still meet it; a button under 4.5:1 must not get worse.
BUTTON_TEXT_BEFORE = {
    "dark": {"btn-primary/primary": 15.15, "btn-primary/secondary": 9.88,
             "btn-danger": 2.78, "btn-success": 9.38, "btn-warning": 12.1},
    "light": {"btn-primary/primary": 1.19, "btn-primary/secondary": 1.83,
              "btn-danger": 2.78, "btn-success": 1.92, "btn-warning": 12.1},
    "darcula": {"btn-primary/primary": 4.54, "btn-primary/secondary": 3.36,
                "btn-danger": 5.36, "btn-success": 4.1, "btn-warning": 5.9},
    "monokai": {"btn-primary/primary": 9.58, "btn-primary/secondary": 9.01,
                "btn-danger": 3.79, "btn-success": 9.58, "btn-warning": 11.71},
    "nord": {"btn-primary/primary": 6.24, "btn-primary/secondary": 4.64,
             "btn-danger": 4.09, "btn-success": 6.13, "btn-warning": 10.68},
    "dracula": {"btn-primary/primary": 5.9, "btn-primary/secondary": 5.97,
                "btn-danger": 3.14, "btn-success": 10.38, "btn-warning": 14.92},
}


def _colour(tokens, ref):
    return tokens[ref] if ref.startswith("--") else parse_color(ref)


@pytest.mark.parametrize("theme", sorted(_themes()))
def test_accent_text_meets_aa_on_every_surface(theme):
    tokens = _themes()[theme]
    failures = [
        f"{fg} {tokens[fg]} on {bg}: {contrast(tokens[fg], tokens[bg]):.2f}"
        for fg in ACCENT_TEXT for bg in BG_TOKENS
        if contrast(tokens[fg], tokens[bg]) < 4.5
    ]
    assert not failures, f"{theme}: " + "; ".join(failures)


@pytest.mark.parametrize("theme", sorted(_themes()))
def test_accent_fill_meets_non_text_contrast(theme):
    tokens = _themes()[theme]
    failures = [
        f"{fill} {tokens[fill]} on {bg}: {contrast(tokens[fill], tokens[bg]):.2f}"
        for fill in ACCENT_FILL for bg in FILL_SURFACES
        if contrast(tokens[fill], tokens[bg]) < 3
    ]
    assert not failures, f"{theme}: " + "; ".join(failures)


@pytest.mark.parametrize("theme", sorted(BUTTON_TEXT_BEFORE))
def test_button_text_contrast_does_not_get_worse(theme):
    tokens = _themes()[theme]
    failures = []
    for name, (fill, text) in BUTTON_TEXT.items():
        ratio = contrast(tokens[fill], _colour(tokens, text))
        floor = min(4.5, BUTTON_TEXT_BEFORE[theme][name])
        if ratio + 0.005 < floor:
            failures.append(f"{name}: {ratio:.2f} < {floor}")
    assert not failures, f"{theme}: " + "; ".join(failures)


STATIC = os.path.dirname(os.path.dirname(CSS))
#: ``color: var(--accent-x)`` paints text with a fill token. ``border-color``
#: and ``background-color`` do not match: the look-behind rejects a hyphen.
# text colour set by a CSS declaration (``color: var(--accent-x)``, also with a
# fallback) or by script (``.style.color = '... var(--accent-x)'``)
_ACCENT_AS_TEXT = re.compile(
    r"(?<![-\w])color(?::\s*|\s*=\s*['\"`][^'\"`]*?)var\(--accent-[a-z]+\s*[),]")


@pytest.mark.parametrize("path", ["css/style.css", "index.html", "js/app.js"])
def test_text_uses_the_accent_text_token(path):
    with open(os.path.join(STATIC, path), encoding="utf-8") as f:
        lines = f.read().splitlines()
    hits = [f"{n}: {line.strip()}" for n, line in enumerate(lines, 1)
            if _ACCENT_AS_TEXT.search(line)]
    assert not hits, f"{path} paints text with a fill token:\n" + "\n".join(hits)


def test_the_text_token_guard_matches_only_text():
    assert _ACCENT_AS_TEXT.search("color: var(--accent-danger)")
    assert _ACCENT_AS_TEXT.search('style="color:var(--accent-primary);"')
    assert not _ACCENT_AS_TEXT.search("border-color: var(--accent-primary)")
    assert not _ACCENT_AS_TEXT.search("background-color: var(--accent-primary)")
    assert not _ACCENT_AS_TEXT.search("color: var(--accent-primary-text)")
    assert _ACCENT_AS_TEXT.search("color: var(--accent-danger, #e74c3c)")
    assert _ACCENT_AS_TEXT.search("status.style.color = 'var(--accent-danger)';")
    assert not _ACCENT_AS_TEXT.search("status.style.color = 'var(--accent-danger-text)';")
    assert not _ACCENT_AS_TEXT.search("el.style.borderColor = 'var(--accent-danger)';")


# --------------------------------------------- text painted on a gradient
#
# A modal header paints its own text on an inline gradient. The gradient is
# not a token, so nothing above measures it: the install-custom-plugin header
# carried ``color: white`` on the danger gradient at 2.78:1 to 3.62:1,
# depending on the theme and on which end of the gradient the glyph sat.
#
# A gradient has no single background colour, so the text must meet 4.5:1 on
# EVERY stop, in EVERY theme. A stop is either a token or a literal.

INDEX = os.path.join(STATIC, "index.html")

#: ``<element ... style="background: linear-gradient(<angle>, <stops>)">``
#: followed, within the header, by a child that sets its own ``color:``.
_GRADIENT = re.compile(
    r"linear-gradient\(\s*[^,]+,\s*(.*?)\)\s*[;\"']")
_STOP = re.compile(r"var\((--[\w-]+)[^)]*\)|(#[0-9a-fA-F]{3,6})")
_TEXT_ON_HEADER = re.compile(
    r'style="color:\s*(var\((--[\w-]+)[^)]*\)|#[0-9a-fA-F]{3,6}|[a-z]+)\s*;?"')


def _header_pairs():
    """(line number, text colour, [gradient stops]) for each header that
    paints text on a gradient it sets inline.

    The pairing is positional and deliberately small: a gradient line, then
    the first following line that sets a text colour inline, inside the same
    header block. Nothing else in this page does that, and a new one that
    does reaches this test by construction.
    """
    with open(INDEX, encoding="utf-8") as f:
        lines = f.read().splitlines()
    pairs = []
    for n, line in enumerate(lines):
        grad = _GRADIENT.search(line)
        if not grad or "modal-header" not in line:
            continue
        stops = [a or b for a, b in _STOP.findall(grad.group(1))]
        for offset in range(1, 4):
            if n + offset >= len(lines):
                break
            text = _TEXT_ON_HEADER.search(lines[n + offset])
            if text:
                pairs.append((n + offset + 1, text.group(1), stops))
                break
    return pairs


def test_a_gradient_header_is_found_at_all():
    """The control. If the page stops matching, every test below passes on an
    empty list and measures nothing."""
    pairs = _header_pairs()
    assert pairs, "no gradient modal header found in index.html"
    for _, _, stops in pairs:
        assert len(stops) >= 2, f"a gradient with fewer than two stops: {stops}"


@pytest.mark.parametrize("theme", sorted(_themes()))
def test_gradient_header_text_meets_aa_on_every_stop(theme):
    tokens = _themes()[theme]
    failures = []
    for line, text, stops in _header_pairs():
        fg = _named(tokens, text)
        for stop in stops:
            bg = _colour(tokens, stop)
            ratio = contrast(fg, bg)
            if ratio < 4.5:
                failures.append(f"index.html:{line} {text} on {stop}: "
                                f"{ratio:.2f}")
    assert not failures, f"{theme}: " + "; ".join(failures)


def _named(tokens, value):
    """A text colour written as a literal: ``var(--x)``, ``#abc`` or the two
    CSS names this page uses. An unknown name fails loudly rather than being
    read as black."""
    inner = re.match(r"var\((--[\w-]+)", value)
    if inner:
        return tokens[inner.group(1)]
    if value in ("white", "black"):
        return parse_color("#ffffff" if value == "white" else "#000000")
    return parse_color(value)


def test_the_gradient_reader_reads_what_the_page_holds():
    """The parser is measured, not assumed: these are the two forms the page
    uses, and the one the fix introduces."""
    stops = _STOP.findall("var(--accent-danger), #ff6b6b")
    assert [a or b for a, b in stops] == ["--accent-danger", "#ff6b6b"]
    assert _TEXT_ON_HEADER.search('style="color: var(--on-danger);"')
    assert _TEXT_ON_HEADER.search('style="color: white;"').group(1) == "white"
