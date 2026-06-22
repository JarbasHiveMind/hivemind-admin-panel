# hivemind-admin-panel
# Copyright (C) 2026 Casimiro Ferreira
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Version information for HiveMind Admin Panel."""

# START_VERSION_BLOCK
VERSION_MAJOR = 0
VERSION_MINOR = 0
VERSION_BUILD = 1
VERSION_ALPHA = 1
# END_VERSION_BLOCK

__version__ = (
    f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_BUILD}"
    + (f"a{VERSION_ALPHA}" if VERSION_ALPHA else "")
)

