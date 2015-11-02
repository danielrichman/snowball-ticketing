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
Utility functions to invoke and clean up the result of lookup operations

:mod:`snowball_ticketing.lookup.connection` powers the actual HTTPS requests
to lookup; this module

* re-names keys to be compatible with the schema
* provides heuristics to guess `person_type`
"""

from __future__ import unicode_literals

import logging
import functools
import gevent.timeout
import gevent.socket
import gevent.ssl
import httplib

from .. import utils
from . import connection


__all__ = ["LookupFailed", "get_crsid"]

logger = utils.getLogger(__name__)


# Selwyn (SEL) has child institutions SELUG, SELPG; and indeed 22 colleges
# in total follow this pattern...
# What's the undergraduate instid for Churchill (CHURCH)?
# You guessed it, CHURUG(!)
# Note most postgrads arn't members of their college + "PG" institution;
# undergrads are, so we assume that "other students" are postgrads

_UGPG_STEM = {
    "CHURCH": "CHUR",
    "GIRTON": "GIRT",
    "HUGHES": "HUGH",
    "EDMUND": "EDM",
    "QUEENS": "QUEN",
    "CLAREH": "CLARH",
    "CORPUS": "CORP",
    "DARWIN": "DAR",
    "CHRISTS": "CHRST"
}

LOOKUP_TIMEOUT = 1


class LookupFailed(Exception):
    """Raised when a lookup operation fails"""
    pass


def _catch_errors(function):
    """
    Decorates `function`
    
    * with a :class:`gevent.timeout.Timeout`
    * raises :class:`LookupFailed` in response to SSL, socket or HTTP
      exceptions; "data" (Key, Value or Type) exceptions, or tiemout
    """
    def wrapper(*args, **kwargs):
        try:
            with gevent.timeout.Timeout(LOOKUP_TIMEOUT):
                return function(*args, **kwargs)
        except (gevent.ssl.SSLError, gevent.socket.error,
                httplib.HTTPException, connection.IbisError):
            logger.exception("Lookup failed (connection)")
            raise LookupFailed
        except gevent.timeout.Timeout:
            logger.exception("Lookup timed out")
            raise LookupFailed
        except (KeyError, TypeError, ValueError, AttributeError):
            logger.exception("Lookup failed (data)")
            raise LookupFailed

    functools.update_wrapper(wrapper, function)
    return wrapper

@_catch_errors
def get_crsid(crsid):
    """
    Retrieve information about a CRSID

    Returns a dict, which may have any subset of the following keys.

    * surname
    * othernames
    * college_instid
    * person_type

    You are guaranteed `surname` and will almost certainly get (a guess at)
    `person_type` (see below).

    `othernames` is from removing the surname from the end of lookup's
    "displayName"; but discarding it if it contains a '.' (since it's
    probably the default value of just the person's initials).

    `person_type` will be one of

    * undergraduate
    * postgraduate
    * alumnus
    * staff
    
    ... and is guessed based on heuristics, including

    * the `instid` (seemingly reliable for undergraduates)
    * the `student` attributes (which are presumed postgraduates if not
      undergrads by the `instid` rule)
    * the `cancelled` and `staff` attributes

    """
    conn = connection.IbisClientConnection()
    response = conn.person(crsid, fetch=["jdCollege", "jdInstid"])

    # basics
    if "person" not in response["result"]:
        raise KeyError("Couldn't find crsid")
    person = response["result"]["person"]

    assert person["identifier"]["scheme"] == "crsid"
    assert person["identifier"]["value"].lower() == crsid.lower()

    surname = person["surname"]
    info = {"surname": surname}

    # unpack other attributes
    attributes = {a["scheme"]: a["value"] for a in person["attributes"]}

    # heuristics
    if "jdCollege" in attributes:
        college = attributes["jdCollege"]
        info["college_instid"] = college

        stem = _UGPG_STEM.get(college, college)
        instid = attributes.get("jdInstid")

        if instid == stem + "UG":
            info["person_type"] = "undergraduate"
        elif instid == stem + "PG":
            info["person_type"] = "postgraduate"

    if person["cancelled"]:
        # for some reason, (at the time of writing 31/07/2013) loads of
        # cancelled ex-students were marked as staff...
        # unfortunately this means we have to assume all cancelled are alumni
        info["person_type"] = "alumnus"

    elif person["student"]:
        # if not a member of the *UG inst, assume postgrad
        info.setdefault("person_type", "postgraduate")

    elif person["staff"]:
        # some postgraduates are marked as staff; prefer "postgraduate"
        info.setdefault("person_type", "staff")

    displayname = person["displayName"]
    if displayname.endswith(surname):
        othernames = displayname[:-len(surname)-1]
        # if this is just initals, don't use them
        # (e.g., before changing my name in lookup mine was "D.J.")
        if "." not in othernames:
            info["othernames"] = othernames

    # debug logging
    log_keys = ("registeredName", "displayName", "jdCollege", "jdInstid")
    log_bools = ("cancelled", "staff", "student")

    def value(k): return person[k] if k in person else attributes.get(k)
    keys = ' '.join("{0}={1}".format(key, value(key))
                    for key in log_keys)
    bools = ' '.join(key for key in log_bools if value(key))
    result = ' '.join("{0}={1}".format(key, value)
                      for key, value in info.iteritems())

    logger.debug("get_crsid(%s)\nresponse %s %s\nresult %s",
                    crsid, keys, bools, result)

    return info
