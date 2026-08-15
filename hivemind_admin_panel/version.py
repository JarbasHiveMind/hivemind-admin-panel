# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
# SPDX-License-Identifier: Apache-2.0
"""Version information for HiveMind Admin Panel."""

# START_VERSION_BLOCK
VERSION_MAJOR = 0
VERSION_MINOR = 1
VERSION_BUILD = 11
VERSION_ALPHA = 4
# END_VERSION_BLOCK

__version__ = (
    f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}"
    + (f"a{VERSION_ALPHA}" if VERSION_ALPHA else "")
)

