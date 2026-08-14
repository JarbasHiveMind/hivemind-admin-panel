# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Guards on requirements.txt that a clean-machine install would otherwise catch.

The HiveMind packages publish alphas only. ``pip`` accepts a prerelease for a
``>=X.Y.Z`` floor only when that floor is itself a prerelease, so a plain
``>=0.9.0`` floor makes ``pip install hivemind-admin-panel`` unresolvable on a
machine that has nothing installed yet.
"""
import os
import re

REQUIREMENTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "requirements.txt")

#: Distributions that ship alphas only.
PRERELEASE_ONLY_PREFIXES = ("hivemind-",)

_REQ = re.compile(r"^([A-Za-z0-9._-]+)\s*(.*)$")


def _requirements():
    with open(REQUIREMENTS) as f:
        for line in f:
            line = line.split("#")[0].strip()
            if not line:
                continue
            m = _REQ.match(line)
            assert m, f"unparsable requirement: {line}"
            yield m.group(1).lower(), m.group(2)


def test_prerelease_only_packages_use_prerelease_floors():
    """A ``>=X.Y.Z`` floor on an alpha-only package cannot be resolved by pip."""
    bad = []
    for name, spec in _requirements():
        if not name.startswith(PRERELEASE_ONLY_PREFIXES):
            continue
        for clause in spec.split(","):
            clause = clause.strip()
            if not clause.startswith(">="):
                continue
            floor = clause[2:].strip()
            if not re.search(r"(a|b|rc)\d+$", floor):
                bad.append(f"{name}{spec}")
    assert not bad, (
        "these floors pin a version that only exists as a prerelease, so a clean "
        f"`pip install` cannot resolve them: {bad}")


def test_every_requirement_has_a_floor_and_a_ceiling_where_declared():
    """Sanity: nothing in requirements.txt is an unbounded bare name."""
    unbounded = [n for n, spec in _requirements() if not spec]
    assert not unbounded, f"requirements without any version constraint: {unbounded}"
