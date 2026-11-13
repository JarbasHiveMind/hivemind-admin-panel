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
                 "${plugin.description}", "${plugin.error", "${error}</span>",
                 # persona solver entry points come from /personas/<name>
                 "monospace;\">${pkg}", "<strong>${ep}</strong>",
                 # server ids come from /servers and sit inside an attribute
                 "id=\"health-${s.id}\""):
        assert sink not in src, f"unescaped interpolation still present: {sink}"


_SERVER_TEXT = re.compile(r"(?<!escapeHtml\()(?<!esc\()\b(?:e|result)\.message\b")

# One innerHTML assignment: from `innerHTML =` or `+=` to the `;` that ends the
# statement at a line end. A template literal split over several lines stays in
# one match, so a sink on a continuation line is still inspected.
_INNERHTML_ASSIGNMENT = re.compile(r"innerHTML\s*\+?=(.*?);[ \t]*$", re.S | re.M)


def _innerhtml_assignments(src):
    for m in _INNERHTML_ASSIGNMENT.finditer(src):
        yield src.count("\n", 0, m.start()) + 1, m.group(1)


def test_server_messages_do_not_reach_innerHTML_unescaped():
    """Test results and error messages carry text the server echoes from user input."""
    offenders = []
    for lineno, body in _innerhtml_assignments(_source()):
        if _SERVER_TEXT.search(body) or "<li>${e}</li>" in body:
            offenders.append(f"app.js:{lineno}: {body.strip()[:120]}")
    assert not offenders, "escape server text before innerHTML:\n  " + "\n  ".join(offenders)


def test_the_innerHTML_guard_sees_a_multiline_template():
    """The guard must not be defeated by moving the sink to a continuation line."""
    sample = "el.innerHTML = `\n  <div>\n    ${result.message}\n  </div>`;\n"
    found = list(_innerhtml_assignments(sample))
    assert found and _SERVER_TEXT.search(found[0][1])


def test_persona_name_is_encoded_in_the_api_path():
    src = _source()
    assert "apiCall(`/personas/${name}`)" not in src


def test_ovos_bus_test_query_is_encoded():
    """Host and port are user input; raw interpolation lets '&' or '#' rewrite the query."""
    src = _source()
    assert "/ovos/test-bus?host=${host}" not in src
    assert "port=${port}" not in src
