# Copyright 2013 Daniel Richman
#
# This file is part of The Snowball Ticketing System.
#
# The Snowball Ticketing System is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# The Snowball Ticketing System is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with The Snowball Ticketing System.  If not, see
# <http://www.gnu.org/licenses/>.

"""
Autoload SQL from ``../queries/``

Particularly long SQL queries are kept in a separate directory (as opposed
to inline in the code that uses them. This module scans that directory on
load and exposes a dict (:data:`queries`) containing the queries.

.. :data:: queries

    Dictionary of long SQL queries.

    The keys correspond to filenames in ``../queries``, without the ``.sql``
    extension; values are file contents (i.e., the query).

"""

import os.path


__all__ = ["queries"]

_queries_dir = os.path.join(os.path.dirname(__file__), '..', 'queries')

queries = {}

for _filename in os.listdir(_queries_dir):
    if not _filename.endswith(".sql"):
        continue
    _path = os.path.join(_queries_dir, _filename)
    _key = _filename[:-4]
    with open(_path) as _f:
        queries[_key] = _f.read()

globals().update(queries)
__all__ += queries.keys()

del _filename, _path, _key
