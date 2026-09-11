# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Static guards on the SPA's HTML escaping.

app.js builds its DOM with template literals assigned to ``innerHTML``. Two
mistakes keep recurring, so both are checked mechanically:

1. An inline handler argument (``onclick="f('${v}')"``) is parsed first as HTML
   and then as JavaScript. ``escapeHtml`` turns ``'`` into ``&#39;``, which the
   HTML parser turns straight back into ``'`` before the JS is compiled — so a
   value containing an apostrophe still breaks out of the string literal.
   Only :func:`jsArg`, which escapes the JS layer first, is safe there.
2. The file used to carry two escape helpers with different character sets.
"""
import os
import re

APP_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "hivemind_admin_panel", "static", "js", "app.js")

_HANDLER_ATTR = re.compile(r'on(?:click|change|input|submit|key\w+)="([^"]*)"')
_QUOTED_ARG = re.compile(r"'\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}'")


def _source():
    with open(APP_JS, encoding="utf-8") as f:
        return f.read()


def test_inline_handler_arguments_all_go_through_jsArg():
    offenders = []
    for lineno, line in enumerate(_source().split("\n"), 1):
        for attr in _HANDLER_ATTR.finditer(line):
            for arg in _QUOTED_ARG.finditer(attr.group(1)):
                expr = arg.group(1).strip()
                if not expr.startswith("jsArg("):
                    offenders.append(f"app.js:{lineno}: {expr}")
    assert not offenders, (
        "inline handler arguments must use jsArg(); escapeHtml() and esc() do not "
        "survive the HTML-then-JS double parse:\n  " + "\n  ".join(offenders))


def test_escape_helpers_do_not_diverge():
    """``esc`` must not be a second, weaker implementation of ``escapeHtml``."""
    src = _source()
    esc_def = re.search(r"function esc\(s\) \{(.+?)\n", src, re.S)
    assert esc_def, "esc() helper not found"
    assert "escapeHtml(" in esc_def.group(1), (
        "esc() must delegate to escapeHtml() so the two cannot drift apart")


def test_known_data_driven_sinks_are_escaped():
    """Values that come from the API must not reach innerHTML unescaped."""
    src = _source()
    for sink in ("${client.name}", "${persona.memory_module}", "${template.name}",
                 "${template.description}", "${health.startup_error", "${plugin.name}",
                 "${plugin.description}", "${plugin.error"):
        assert sink not in src, f"unescaped interpolation still present: {sink}"
