# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Every theme keeps body and muted text readable on every panel surface.

WCAG 2.x requires a contrast ratio of 4.5:1 for normal text. A theme block
sets only the tokens it changes and inherits the rest from ``:root``.
"""
import os
import re

import pytest

CSS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "hivemind_admin_panel", "static", "css", "style.css")

TEXT_TOKENS = ("--text-primary", "--text-secondary")
BG_TOKENS = ("--bg-primary", "--bg-secondary", "--bg-card", "--bg-hover")
_BLOCK = re.compile(r'(:root|\[data-theme="([\w-]+)"\])\s*\{([^}]*)\}')
_VAR = re.compile(r"(--[\w-]+):\s*(#[0-9a-fA-F]{6})\b")


def _themes():
    with open(CSS, encoding="utf-8") as f:
        css = f.read()
    raw = {}
    for m in _BLOCK.finditer(css):
        name = m.group(2) or "dark"
        raw.setdefault(name, {}).update(_VAR.findall(m.group(3)))
    base = raw["dark"]
    return {name: {**base, **tokens} for name, tokens in raw.items()}


def _luminance(hex_color):
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_ratio_matches_known_values():
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)


def test_all_themes_are_parsed():
    assert {"dark", "light", "darcula", "monokai", "nord", "dracula"} <= set(_themes())


@pytest.mark.parametrize("theme", sorted(_themes()))
def test_text_tokens_meet_aa_on_every_surface(theme):
    tokens = _themes()[theme]
    failures = [
        f"{fg} {tokens[fg]} on {bg} {tokens[bg]}: {contrast(tokens[fg], tokens[bg]):.2f}"
        for fg in TEXT_TOKENS for bg in BG_TOKENS
        if contrast(tokens[fg], tokens[bg]) < 4.5
    ]
    assert not failures, f"{theme}: " + "; ".join(failures)
