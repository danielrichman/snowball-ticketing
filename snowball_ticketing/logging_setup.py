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

"""Functions to set up Python logging"""

import logging
from logging.handlers import SysLogHandler, SMTPHandler

from . import utils


__all__ = ["add_postgresql_handler", "remove_gunicorn_syslog_handler",
           "add_syslog_handler", "add_smtp_handler"]


_format_string = "%(name)s %(levelname)s " \
                    "(%(remote_addr)s %(flask_endpoint)s " \
                    "%(session_id)s %(user_id)s) %(message)s"

_format_email = \
"""%(levelname)s from logger %(name)s

Time:       %(asctime)s
Location:   %(pathname)s:%(lineno)d
Module:     %(module)s
Function:   %(funcName)s

Request:    %(request_path)s
Endpoint:   %(flask_endpoint)s
Client:     %(remote_addr)s
Session ID: %(session_id)s
User ID:    %(user_id)s

%(message)s"""


def add_postgresql_handler(postgres, level=logging.INFO):
    """adds :class:`utils.PostgreSQLHandler` using postgres config `postgres`"""
    handler = utils.PostgreSQLHandler(postgres)
    handler.setLevel(level)
    logger = logging.getLogger("snowball_ticketing")
    logger.addHandler(handler)

def remove_gunicorn_syslog_handler():
    """
    Remove the gunicorn SysLog handler from gunicorn.error

    gunicorn is set up to log gunicorn.error to syslog, in order to catch
    errors from before the app is loaded. Detach it.
    """
    gunicorn_error_logger = logging.getLogger("gunicorn.error")
    for hdlr in gunicorn_error_logger.handlers[:]:
        if isinstance(hdlr, SysLogHandler):
            gunicorn_error_logger.removeHandler(hdlr)

def add_syslog_handler(level=logging.DEBUG):
    """Add a syslog (local5) handler to the root logger"""
    handler = SysLogHandler(facility=SysLogHandler.LOG_LOCAL5,
                            address="/dev/log")
    handler.setLevel(level)
    handler.setFormatter(utils.OptionalKeysFormatter(_format_string))

    logger = logging.getLogger()
    logger.setLevel(min(level, logger.level))
    logger.addHandler(handler)

def add_smtp_handler(level=logging.ERROR, server="localhost",
                     from_="www-ticketing@localhost", to="root@localhost",
                     subject="Snowball Ticketing error logger"):
    """Add a SMTP handler to the root logger"""
    handler = SMTPHandler(server, from_, to, subject)
    handler.setLevel(level)
    handler.setFormatter(utils.OptionalKeysFormatter(_format_email))

    logger = logging.getLogger()
    logger.setLevel(min(level, logger.level))
    logger.addHandler(handler)
