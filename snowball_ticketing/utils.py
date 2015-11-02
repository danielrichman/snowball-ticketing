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

"""Miscellaneous utilities"""

from __future__ import unicode_literals, division

import os
import sys
import string
import base64
import datetime
import logging
import functools
import contextlib
import email.mime.text
import email.utils
import smtplib
import textwrap
import traceback
import threading

import flask
import jinja2
import jinja2.ext
from werkzeug.datastructures import ImmutableDict
from werkzeug.local import LocalProxy
import werkzeug.exceptions
import psycopg2
import psycopg2.extras
import psycopg2.extensions
import pytz


__all__ = ["LoggerAdaptor", "PostgreSQLHandler", "OptionalKeysFormatter",
           "getLogger",
           "postgres", "PostgreSQLConnection", "PostgreSQL", "with_savepoint",
           "SessionInvalid", "SessionExpired", "SessionAbsent",
           "SessionUserDetailsIncomplete", "SessionUserDisabled",
           "BadSession", "SessionInterface", "SessionInstance",
           "requires_session",
           "gen_secret", "customise_jinja",
           "add_history_urls", "sif", "format_datetime",
           "pounds_pence", "plural", "college_name",
           "send_email", "RewrapExtension",
           "BadCSRFSecret", "BadAJAXSecret", "check_csrf", "requires_csrf",
           "check_ajax", "requires_ajax",
           "all_colleges",
           "parse_matriculation_year", "MatriculationTimetravel",
           "MatriculationImplausible"]


#: proxy to the :class:`PostgreSQL` object attached to the current app
postgres = LocalProxy(lambda: flask.current_app.snowball_postgresql)

# misc_logger created below LoggerAdaptor
pytz_bst = pytz.timezone("Europe/London")
b64_trans = string.maketrans(b"+/=", b"-._")

_colleges_cache = None


class LoggerAdaptor(logging.LoggerAdapter):
    """
    A :class:`logging.LoggerAdapter` that adds request context

    Adds the following attributes to log records (which can then be used in a
    :class:`logging.Formatter` string).

    * base_url: ``flask.request.base_url``
    * flask_endpoint: ``flask.request.endpoint``
    * remote_addr: ``flask.request.remote_addr``
    * session_id: ``flask.session["session_id"]``
    * user_id: ``flask.session["user_id"]``

    Relevant properties will be None, if there is no request context,
    or the session is bad.
    """

    def __init__(self, logger):
        super(LoggerAdaptor, self).__init__(logger, None)

    def process(self, msg, kwargs):
        try:
            add = {"request_path": None, "flask_endpoint": None,
                   "remote_addr": None, "session_id": None, "user_id": None}

            if flask.has_request_context():
                add["request_path"] = flask.request.path
                add["flask_endpoint"] = flask.request.endpoint
                add["remote_addr"] = flask.request.remote_addr
                # in messages emitted by open_session, flask.session is None
                if getattr(flask.session, "ok", False):
                    add["session_id"] = flask.session["session_id"]
                    add["user_id"] = flask.session["user_id"]

            extra = kwargs.setdefault("extra", {})
            for key in add:
                if key not in extra:
                    extra[key] = add[key]

        except Exception as e:
            traceback.print_exc()

        return msg, kwargs

class PostgreSQLHandler(logging.Handler):
    """
    A :class:`logging.Handler` that logs to the `log` PostgreSQL table

    Does not use :class:`PostgreSQL`, keeping its own connection, in autocommit
    mode.

    .. DANGER:

        Beware explicit or automatic locks taken out in the main requests'
        transaction could deadlock with this INSERT!

        In general, avoid touching the log table entirely. SELECT queries
        do not appear to block with INSERTs. If possible, touch the log table
        in autocommit mode only.

    `db_settings` is passed to :meth:`psycopg2.connect` as kwargs
    (``connect(**db_settings)``).
    """

    _query = "INSERT INTO log " \
                "(created, level, logger, message, function, " \
                " filename, line_no, traceback, " \
                " request_path, flask_endpoint, remote_addr, " \
                " session_id, user_id) " \
             "VALUES " \
                "(utcnow(), %(level)s, %(logger)s, " \
                " %(message)s, %(function)s, %(filename)s, " \
                " %(line_no)s, %(traceback)s, " \
                " %(request_path)s, %(flask_endpoint)s, %(remote_addr)s, " \
                " %(session_id)s, %(user_id)s)"

    # see TYPE log_level
    _levels = ('debug', 'info', 'warning', 'error', 'critical')

    def __init__(self, db_settings):
        super(PostgreSQLHandler, self).__init__()
        self.db_settings = db_settings
        self.connection = None
        self.cursor = None

    def emit(self, record):
        try:
            level = record.levelname.lower()
            if level not in self._levels:
                level = "debug"

            if record.exc_info:
                lines = traceback.format_exception(*record.exc_info)
                traceback_text = ''.join(lines)
            else:
                traceback_text = None

            args = {
                "level": level,
                "message": record.getMessage(),
                "logger": record.name,
                "function": record.funcName,
                "filename": record.pathname,
                "line_no": record.lineno,
                "traceback": traceback_text,
                "request_path": getattr(record, "request_path", None),
                "flask_endpoint": getattr(record, "flask_endpoint", None),
                "remote_addr": getattr(record, "remote_addr", None),
                "session_id": getattr(record, "session_id", None),
                "user_id": getattr(record, "user_id", None)
            }

            try:
                if self.connection is None:
                    raise psycopg2.OperationalError

                self.cursor.execute(self._query, args)

            except psycopg2.OperationalError:
                self.connection = psycopg2.connect(**self.db_settings)
                self.connection.autocommit = True
                self.cursor = self.connection.cursor()

                self.cursor.execute(self._query, args)

        except Exception:
            self.handleError(record)

class OptionalKeysFormatter(logging.Formatter):
    """
    Adapt LogRecords that haven't come from :class:`LoggerAdaptor`
    
    This is a :class:`logging.Formatter` that fills in the keys that
    :class:`LoggerAdaptor` adds with ``None`` if they are not already set,
    so that the same formatter may be used for records from
    :class:`LoggerAdaptor` and regular loggers.
    """

    fill_keys = ("request_path", "flask_endpoint", "remote_addr",
                 "session_id", "user_id")

    def format(self, record):
        for key in self.fill_keys:
            if not hasattr(record, key):
                setattr(record, key, None)

        return super(OptionalKeysFormatter, self).format(record)

def getLogger(name):
    """:func:`logging.getLogger`, but returns :class:`LoggerAdaptor` objects"""
    return LoggerAdaptor(logging.getLogger(name))

misc_logger = getLogger(__name__)


class PostgreSQLConnection(psycopg2.extensions.connection):
    """
    A custom `connection_factory` for :func:`psycopg2.connect`.

    This modifies the :meth:`cursor` method of a :class:`psycopg2.connection`,
    facilitating easy acquiring of cursors made from
    :class:`psycopg2.extras.RealDictCursor`.
    """

    def __init__(self, *args, **kwargs):
        super(PostgreSQLConnection, self).__init__(*args, **kwargs)
        for type in (psycopg2.extensions.UNICODE,
                     psycopg2.extensions.UNICODEARRAY):
            psycopg2.extensions.register_type(type, self)

    def cursor(self, real_dict_cursor=False):
        """
        Get a new cursor.

        If real_dict_cursor is set, a RealDictCursor is returned
        """

        kwargs = {}
        if real_dict_cursor:
            kwargs["cursor_factory"] = psycopg2.extras.RealDictCursor
        return super(PostgreSQLConnection, self).cursor(**kwargs)

class PostgreSQL(object):
    """
    A PostgreSQL helper extension for Flask apps

    On initialisation it adds an after_request function that commits the
    transaction (so that if the transaction rolls back the request will
    fail) and a app context teardown function that disconnects any active
    connection.

    You can of course (and indeed should) use :meth:`commit` if you need to
    ensure some changes have made it to the database before performing
    some other action. :meth:`teardown` is also available to be called
    directly.

    Connections are created by ``psycopg2.connect(**app.config["POSTGRES"])``
    (e.g., ``app.config["POSTGRES"] = {"database": "mydb"}``),
    are pooled (you can adjust the pool size with `pool`) and are tested for
    server shutdown before being given to the request.
    """

    def __init__(self, app=None, pool_size=2):
        self.app = app
        self._pool = []
        self.pool_size = pool_size
        self._lock = threading.RLock()
        self.logger = getLogger(__name__ + ".PostgreSQL")

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """
        Initialises the app by adding hooks

        * Hook: ``app.after_request(self.commit)``
        * Hook: ``app.teardown_appcontext(self.teardown)``
        """

        app.after_request(self.commit)
        app.teardown_appcontext(self.teardown)
        app.snowball_postgresql = self

    def _connect(self):
        """Returns a connection to the database"""

        with self._lock:
            c = None

            if len(self._pool):
                c = self._pool.pop()
                try:
                    # This tests if the connection is still alive.
                    c.reset()
                except psycopg2.OperationalError:
                    self.logger.debug("assuming pool dead", exc_info=True)

                    # assume that the entire pool is dead
                    try:
                        c.close()
                    except psycopg2.OperationalError:
                        pass

                    for c in self._pool:
                        try:
                            c.close()
                        except psycopg2.OperationalError:
                            pass

                    self._pool = []
                    c = None
                else:
                    self.logger.debug("got connection from pool")

            if c is None:
                c = self._new_connection()

        return c

    def _new_connection(self):
        """Create a new connection to the database"""
        s = flask.current_app.config["POSTGRES"]
        summary = ' '.join(k + "=" + v for k, v in s.iteritems())
        self.logger.debug("connecting (%s)", summary)
        c = psycopg2.connect(connection_factory=PostgreSQLConnection, **s)
        return c

    @property
    def connection(self):
        """
        Gets the PostgreSQL connection for this Flask request

        If no connection has been used in this request, it connects to the
        database. Further use of this property will reference the same
        connection

        The connection is committed and closed at the end of the request.
        """

        g = flask.g
        if not hasattr(g, '_postgresql'):
            g._postgresql = self._connect()
        return g._postgresql

    def cursor(self, real_dict_cursor=False):
        """
        Get a new postgres cursor for immediate use during a request

        If a cursor has not yet been used in this request, it connects to the
        database. Further cursors re-use the per-request connection.

        The connection is committed and closed at the end of the request.

        If real_dict_cursor is set, a RealDictCursor is returned
        """

        return self.connection.cursor(real_dict_cursor)

    def commit(self, response=None):
        """
        (Almost an) alias for self.connection.commit()

        ... except if self.connection has never been used this is a noop
        (i.e., it does nothing)

        Returns `response` unmodified, so that this may be used as an
        :meth:`flask.after_request` function.
        """
        g = flask.g
        if hasattr(g, '_postgresql'):
            self.logger.debug("committing")
            g._postgresql.commit()
        return response

    def teardown(self, exception):
        """Either return the connection to the pool or close it"""
        g = flask.g
        if hasattr(g, '_postgresql'):
            c = g._postgresql
            del g._postgresql

            with self._lock:
                s = len(self._pool)
                if s >= self.pool_size:
                    self.logger.debug("teardown: pool size %i - closing", s)
                    c.close()
                else:
                    self.logger.debug("teardown: adding to pool, new size %i",
                                      s + 1)
                    c.reset()
                    self._pool.append(c)

@contextlib.contextmanager
def with_savepoint(name, pg=postgres):
    """
    A context manager that wraps database queries in a PostgreSQL savepoint

    Usage::

        with with_savepoint('my_savepoint') as rollback:
            do_something()
            if something:
                rollback()  # rolls back to the start of the with block

    `pg` should be a :class:`psycopg2.connection` or :class:`PostgreSQL`.
    """

    with pg.cursor() as cur:
        cur.execute("SAVEPOINT " + name)

        def rollback():
            cur.execute("ROLLBACK TO SAVEPOINT " + name)

        try:
            yield rollback
        except Exception:
            raising = True
            raise
        else:
            raising = False
        finally:
            try:
                cur.execute("RELEASE SAVEPOINT " + name)
            except Exception:
                # don't squash the original exception
                if not raising:
                    raise
                else:
                    misc_logger.exception("suppressing exception")


# alas, my pull request has not been merged:
# https://github.com/mitsuhiko/flask/pull/839
#
# class SessionInvalid(werkzeug.exceptions.Forbidden):
#    ...
#    Since it is a subclass of :class:`werkzeug.exceptions.Forbidden`, it being
#    raised by :meth:`Session.require` can abort the request with 403 Forbidden.
#    ...

class SessionInvalid(Exception):
    """
    Base class for Session load errors

    Also used (i.e., not a subclass) if the cookie exists but has been
    tampered with.
    """

class SessionExpired(SessionInvalid):
    """Session has expired"""

class SessionAbsent(SessionInvalid):
    """Session cookie missing"""

class SessionUserDetailsIncomplete(SessionInvalid):
    """User is incomplete and can't be used yet"""

class SessionUserDisabled(SessionInvalid):
    """Current session user is disabled (``enable_login == False``)"""

class BadSession(object):
    """
    Object used to represent that loading a session failed

    .. attribute:: reason

        An exception class, representing the reason loading failed

    """
    def __init__(self, reason):
        self.reason = reason

    def __getitem__(self, key):
        """Raises :attr:`self.reason`"""
        raise self.reason

class SessionInterface(flask.sessions.SessionInterface):
    """
    Thin interface that just spawns :class:`SessionInstace` objects`

    To allow calling methods such as :meth:`SessionInstance.new` via
    :attr:`flask.session`, this :class:`flask.sessions.SessionInterface`
    simply spawns :class:`SessionInstance` objects, which contain the main
    logic.

    `pg` should be a :class:`PostgreSQL`.
    """

    def __init__(self, pg=postgres):
        super(SessionInterface, self).__init__()
        self.postgres = pg
        self.logger = getLogger(__name__ + ".session")

    def open_session(self, app, request):
        """Creates a :class:`SessionInstance`"""
        self.logger.debug("open_session")
        return SessionInstance(self, app, request)

    def save_session(self, app, session, response):
        """Save/delete cookies (act on session.modified and session.cookie)"""

        if not session.modified:
            return

        value = session.cookie

        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)

        self.logger.debug("cookie name=%s domain=%s path=%s",
                          app.session_cookie_name, domain, path)

        if value is None:
            self.logger.debug("delete_cookie")
            response.delete_cookie(app.session_cookie_name,
                                   domain=domain, path=path)
            return

        httponly = self.get_cookie_httponly(app)
        secure = self.get_cookie_secure(app)

        self.logger.debug("set_cookie")
        response.set_cookie(app.session_cookie_name, value,
                            domain=domain, path=path,
                            httponly=httponly, secure=secure)

class SessionInstance(object):
    """
    Creates and checks rows in the `sessions` table.

    The default flask interface is vulnerable to replaying old cookies,
    so we store sessions in PostgreSQL. Storing arbitrary keys could, but has
    not, been implemented, so only certain keys are available (see schema).

    An instance of this object will behave like an immutable dict when a
    session has been loaded. In addition, it has methods on it that will
    create or remove rows.

    It will attempt to load a session (by checking a request cookie) 
    when instantiated by the :class:`SessionInterface` at the beginning of
    every request. The :class:`SessionInterface` also calls :meth:`set_cookies`
    at the end of each request.

    Browser cookies are set to expire at the end of the session
    (_permanent is not implemented), and we refuse to load sessions if the
    `last` column in the `sessions` table is before now - 1 day.
    """

    def __init__(self, session_interface, app, request):
        self.modified = False
        self.new = self.permanent = False   # flask requirements
        self._session = None

        self.postgres = session_interface.postgres
        self.logger = session_interface.logger
        self._load(app, request)

    def create(self, user):
        """
        Creates a new session

        * asserts that no session currently exists
        * creates a row in the `sessions` table
        * sets a session cookie
        * populates :attr:`user_id`, :attr:`secret`, etc.

        """

        if self.ok:
            raise RuntimeError("a session already exists")

        query = "INSERT INTO sessions " \
                "(user_id, secret, csrf_secret, ajax_secret, created, last) " \
                "VALUES (%s, %s, %s, %s, utcnow(), utcnow()) " \
                "RETURNING *"

        with self.postgres.cursor(True) as cur:
            a = (user["user_id"], gen_secret(), gen_secret(), gen_secret())
            cur.execute(query, a)
            assert cur.rowcount == 1
            self._session = cur.fetchone()

        self._session["user"] = user
        self.logger.info("Created session session_id=%s user_id=%s",
                         self._session["session_id"], user["user_id"])

        self.modified = True

    def _load(self, app, request):
        """
        Setup method

        Loads the session from the database, or stores a BadSession object
        in its place to note that the loading failed.

        Note: the act of loading the session includes updating the expires
        column!
        """

        assert self._session is None

        try:
            cookie = request.cookies[app.session_cookie_name]
        except KeyError:
            self._session = BadSession(SessionAbsent)
            return

        session_id, _, secret = cookie.partition("|")

        try:
            if _ != "|":
                raise ValueError("partition failed")
            session_id = int(session_id)
        except ValueError as reason:
            self._session = BadSession(SessionInvalid)
            self.modified = True
            self.logger.warning("Invalid session cookie: %s", reason)
            return

        query1 = "SELECT *, " \
                    "last + '1 day'::interval < utcnow() AS expired " \
                 "FROM sessions " \
                 "WHERE session_id = %s AND secret = %s AND NOT destroyed"
        query2 = "UPDATE sessions " \
                 "SET last = utcnow() " \
                 "WHERE session_id = %s " \
                 "RETURNING last"
        # easier to not use a JOIN in query1 to simplify getting the user
        # object with the DictCursor
        query3 = "SELECT * FROM users WHERE user_id = %s"

        with self.postgres.cursor(True) as cur:
            cur.execute(query1, (session_id, secret))
            if cur.rowcount != 1:
                self.logger.warning("bad session_id, bad secret or session "
                                    "destroyed (session %s)", session_id)
                self._session = BadSession(SessionInvalid)
                self.modified = True
                return

            session = cur.fetchone()

            if session["expired"]:
                self.logger.warning("Session expired session_id=%s user_id=%s",
                                    session_id, session["user_id"])
                self._session = BadSession(SessionExpired)
                self.modified = True
                return

            cur.execute(query2, (session_id, ))
            session.update(cur.fetchone())

            cur.execute(query3, (session["user_id"], ))
            assert cur.rowcount == 1
            session["user"] = cur.fetchone()

        self.logger.debug("Session loaded session_id=%s user_id=%s",
                          session_id, session["user_id"])
        self._session = session

    def destroy(self):
        """Ends the current session, deleting its cookie and database row"""

        assert self.ok

        self.logger.info("destroying current session")

        query = "UPDATE sessions SET destroyed = TRUE WHERE session_id = %s"
        with self.postgres.cursor() as cur:
            cur.execute(query, (self["session_id"], ))
            assert cur.rowcount == 1

        self._session = BadSession(SessionAbsent)
        self.modified = True

    @property
    def ok(self):
        """
        :class:`bool`: is a valid session present?

        Does not check `details_complete`; see :meth:`require`.
        """
        s = self._session
        assert isinstance(s, BadSession) or isinstance(s, dict)
        return not isinstance(s, BadSession)

    @property
    def cookie(self):
        """The contents of the session cookie"""
        if self.ok:
            return "{0}|{1}".format(self["session_id"], self["secret"])
        else:
            return None

    def require(self, details_completed=True):
        """
        Asserts the presence of a valid session

        If `details_completed` is True, we also require that
        self["user"]["details_complete"] be true.

        Raises :exc:`SessionInvalid`, :exc:`SessionAbsent`,
        :exc:`SessionExpired`, :exc:`SessionUserDetailsIncomplete`,
        :exc:`SessionUserDisabled`, as appropriate.
        """
        s = self._session
        if isinstance(s, BadSession):
            self.logger.warning("rejecting: session required")
            raise s.reason
        elif not s["user"]["enable_login"]:
            self.logger.warning("rejecting: session user %s has "
                                "enable_login=False", s["user"]["user_id"])
            raise SessionUserDisabled
        elif details_completed and not s["user"]["details_completed"]:
            self.logger.warning("rejecting: session with details complete "
                                "required (user %s)", s["user"]["user_id"])
            raise SessionUserDetailsIncomplete
        else:
            assert isinstance(s, dict)

    def __getitem__(self, key):
        """Proxy to self._session[key]"""
        return self._session[key]

def requires_session(function):
    """Function decorator that calls `flask.session.require` first"""

    def wrapper(*args, **kwargs):
        flask.session.require()
        return function(*args, **kwargs)

    functools.update_wrapper(wrapper, function)
    return wrapper


def gen_secret():
    """Returns a randomly generated string"""
    return base64.b64encode(os.urandom(15)).translate(b64_trans)

def customise_jinja(app):
    """
    Common Jinja settings

    * set undefined to :class:`jinja2.StrictUndefined`
    * add template filters :func:`add_history_urls`, :func:`sif`,
      :func:`format_datetime`, :func:`pounds_pence`, :func:`plural` and
      :func:`college_name`
    * add template globals 'now' (:meth:`datetime.datetime.utcnow`)
      and :func:`all_colleges`

    """

    app.jinja_options = dict(app.jinja_options)
    app.jinja_options['undefined'] = jinja2.StrictUndefined
    app.add_template_filter(add_history_urls)
    app.add_template_filter(sif)
    app.add_template_filter(format_datetime)
    app.add_template_filter(pounds_pence)
    app.add_template_filter(plural)
    app.add_template_filter(college_name)
    app.add_template_global(datetime.datetime.utcnow, name="now")
    app.add_template_global(all_colleges)

def add_history_urls(section_titles, endpoint):
    """
    Look up the URLs that should be used for each section.
    
    Takes a dict mapping sections to page titles, and produces a dict mapping
    sections to ``{title: t, url: u}`` dicts, where `u` is determined using
    ``flask.url_for(endpoint, section=s)``.
    """
    out = {}
    for section, title in section_titles.iteritems():
        url = flask.url_for(endpoint, section=section)
        out[section] = {"title": title, "url": url}
    return out

def sif(variable, val):
    """"string if": `val` if `variable` is defined and truthy, else ''"""
    if not jinja2.is_undefined(variable) and variable:
        return val
    else:
        return ""

def format_datetime(what, format_name="nice short",
                    custom_format=None, convert_bst=True):
    """
    Jinja2 filter to turn a date or datetime into a string

    If `what` is a datetime, it must be timezone-naive
    (as far as python is concerned), but its values must be UTC.

    Either pick `format_name` from the options below, or provide
    `custom_format`

    * ``full+tz``: 2013-08-07 18:23:46 BST+0100
    * ``full``: 2013-08-07 18:24:12
    * ``nice``: Wednesday 07 August 2013 at 18:24:37
    * ``nice short``: Wed 07 Aug at 18:24
    * ``date``: 2013-08-07
    * ``date nice``: Wednesday 07 August 2013
    * ``date nice short``: Wed 07 Aug

    """

    formats = {
        "full+tz": "%Y-%m-%d %H:%M:%S %Z%z",
        "full": "%Y-%m-%d %H:%M:%S",
        "nice": "%A %d %B %Y at %H:%M:%S",
        "nice short": "%a %d %b at %H:%M",
        "date": "%Y-%m-%d",
        "date nice": "%A %d %B %Y",
        "date nice short": "%a %d %b",
    }

    if custom_format is not None:
        format = custom_format
    else:
        format = formats[format_name]

    if hasattr(what, "tzinfo"):
        what = what.replace(tzinfo=pytz.utc)
        if convert_bst:
            what = what.astimezone(pytz_bst)

    return what.strftime(format)

def plural(what, number, plural=None):
    """``(plural or what + 's') if number != 1 else what``"""
    if number != 1:
        if plural:
            return plural
        else:
            return what + 's'
    else:
        return what

def pounds_pence(pence, allow_short=False):
    """
    Returns a string representing `pence`, in form (poundsign)123,456.78

    If `allow_short` is true, and the pence part is zero, the decimal place
    and zeros after it will be omitted.
    """
    if pence < 0:
        sign = "-"
    else:
        sign = ""
    pence = abs(pence)
    pounds = pence // 100
    pence %= 100
    if allow_short and pence == 0:
        return "{0}\u00a3{1:,d}".format(sign, pounds)
    else:
        return "{0}\u00a3{1:,d}.{2:02d}".format(sign, pounds, pence)

def college_name(college_id, pg=postgres):
    """
    Looks up the name of a single college from its id, `college_id`
    
    Returns ``""`` if college_id is ``None``.
    """
    if college_id is None:
        return ''
    else:
        return all_colleges(pg=pg)[college_id]

def all_colleges(pg=postgres):
    """Get a dict mapping college_id -> college_name"""

    global _colleges_cache

    query = "SELECT college_id, name FROM colleges"

    if _colleges_cache is None:
        misc_logger.debug("loading colleges list")

        with pg.cursor() as cur:
            cur.execute(query)
            _colleges_cache = ImmutableDict(cur)

    return _colleges_cache


def send_email(template_name, recipient,
              sender=("Snowball Ticketing", "ticketing@selwynsnowball.co.uk"),
              **kwargs):
    """
    Send an email, acquiring its payload by rendering a jinja2 template

    :type template: :class:`str`
    :param template: name of the template file in ``templates/emails`` to use
    :type recipient: :class:`tuple` (:class:`str`, :class:`str`)
    :param recipient: 'To' (name, email)
    :type sender: :class:`tuple` (:class:`str`, :class:`str`)
    :param sender: 'From' (name, email)

    * `recipient` and `sender` are made available to the template as variables
    * In any email tuple, name may be ``None``
    * The subject is retrieved from a sufficiently-global template variable;
      typically set by placing something like
      ``{% set subject = "My Subject" %}``
      at the top of the template used (it may be inside some blocks
      (if, elif, ...) but not others (rewrap, block, ...).
      If it's not present, it defaults to "Snowball Ticketing".
    * With regards to line lengths: :class:`email.mime.text.MIMEText` will
      (at least, in 2.7) encode the body of the text in base64 before sending
      it, text-wrapping the base64 data. You will therefore not have any
      problems with SMTP line length restrictions, and any concern to line
      lengths is purely aesthetic or to be nice to the MUA.
      :class:`RewrapExtension` may be used to wrap blocks of text nicely.
      Note that ``{{ variables }}`` in manually wrapped text can cause
      problems!

    """

    if flask.current_app:
        # use the app's env if it's available, so that url_for may be used
        jinja_env = flask.current_app.jinja_env
    else:
        path = os.path.join(os.path.dirname(__file__), '..', 'templates')
        loader = jinja2.FileSystemLoader(path)
        jinja_env = jinja2.Environment(loader=loader,
                extensions=['jinja2.ext.autoescape', 'jinja2.ext.with_'])

        jinja_env.filters["sif"] = sif
        jinja_env.filters["format_datetime"] = format_datetime
        jinja_env.filters["pounds_pence"] = pounds_pence
        jinja_env.filters["plural"] = plural
        jinja_env.globals["now"] = datetime.datetime.utcnow

    jinja_env = jinja_env.overlay(autoescape=False,
                                  extensions=[RewrapExtension])

    def _jinja2_email(name, email):
        if name is None:
            hint = 'name was not set for email {0}'.format(email)
            name = jinja_env.undefined(name='name', hint=hint)
        return {"name": name, "email": email}

    template = jinja_env.get_template(os.path.join('emails', template_name))

    kwargs["sender"] = _jinja2_email(*sender)
    kwargs["recipient"] = _jinja2_email(*recipient)

    rendered = template.make_module(vars=kwargs)

    message = email.mime.text.MIMEText(unicode(rendered), _charset='utf-8')
    message["From"] = email.utils.formataddr(sender)
    message["To"] = email.utils.formataddr(recipient)
    message["Subject"] = getattr(rendered, "subject", "Snowball Ticketing")

    misc_logger.info("mailing template %s to %s", template_name, recipient[1])

    s = smtplib.SMTP('localhost')
    s.sendmail(sender[1], [recipient[1]], message.as_string())
    s.quit()

class RewrapExtension(jinja2.ext.Extension):
    """
    The :mod:`jinja2` extension adds a ``{% rewrap %}...{% endrewrap %}`` block

    The contents in the rewrap block are modified as follows

    * whitespace at the start and end of lines is discarded
    * the contents are split into 'paragraphs' separated by blank lines
    * empty paragraphs are discarded - so two blank lines is equivalent to
      one blank line, and blank lines at the start and end of the block
      are effectively discarded
    * lines in each paragraph are joined to one line, and then text wrapped
      to lines `width` characters wide
    * paragraphs are re-joined into text, with blank lines insert in between
      them

    It does not insert a newline at the end of the block, which means that::

        Something, then a blank line

        {% block rewrap %}
        some text
        {% endblock %}

        After another blank line

    will do what you expect.

    You may optionally specify the width like so::

        {% rewrap 72 %}

    It defaults to 78.    
    """

    tags = set(['rewrap'])

    def parse(self, parser):
        # first token is 'rewrap'
        lineno = parser.stream.next().lineno

        if parser.stream.current.type != 'block_end':
            width = parser.parse_expression()
        else:
            width = jinja2.nodes.Const(78)

        body = parser.parse_statements(['name:endrewrap'], drop_needle=True)

        call = self.call_method('_rewrap', [width])
        return jinja2.nodes.CallBlock(call, [], [], body).set_lineno(lineno)

    def _rewrap(self, width, caller):
        contents = caller()
        lines = [line.strip() for line in contents.splitlines()]
        lines.append('')

        paragraphs = []
        start = 0
        while start != len(lines):
            end = lines.index('', start)
            if start != end:
                paragraph = ' '.join(lines[start:end])
                paragraphs.append(paragraph)
            start = end + 1

        new_lines = []

        for paragraph in paragraphs:
            if new_lines:
                new_lines.append('')
            new_lines += textwrap.wrap(paragraph, width)

        # under the assumption that there will be a newline immediately after
        # the endrewrap block, don't put a newline on the end.
        return '\n'.join(new_lines)


class BadCSRFSecret(werkzeug.exceptions.BadRequest):
    """``request.form['csrf_secret']`` was invalid"""

class BadAJAXSecret(werkzeug.exceptions.BadRequest):
    """``request.values['ajax_secret']`` was invalid"""

def check_csrf(request=flask.request, session=flask.session):
    """
    Checks ``csrf_secret`` (for POST requests)

    Before the view is executed, 
    If the request method was POST, this function checks
    ``request.form["csrf_secret"]`` against ``session["csrf_secret"]``
    and raises :exc:`BadCSRFSecret` if it does not match.
    """

    # the default kwargs work because flask.request and flask.session are
    # proxy objects and the module attribute itself doesn't change request to
    # request

    if request.method == "POST":
        if "csrf_secret" not in request.form:
            misc_logger.warning("csrf_secret absent")
            raise BadCSRFSecret
        session.require(False)
        if request.form["csrf_secret"] != session["csrf_secret"]:
            misc_logger.warning("csrf_secret bad")
            raise BadCSRFSecret
    else:
        assert request.form == {}

def requires_csrf(view_function):
    """Decorator that calls :meth:`check_csrf` before the view function"""

    def wrapper(*args, **kwargs):
        check_csrf()
        return view_function(*args, **kwargs)

    functools.update_wrapper(wrapper, view_function)
    return wrapper

def check_ajax(request=flask.request, session=flask.session):
    """
    Checks the ``ajax_secret``

    This function checks ``request.values["ajax_secret"]`` against
    ``session["ajax_secret"]``.

    Note ``request.values`` is a combination of ``request.form`` and
    ``request.args``, so the secret may appear in either.
    """

    if "ajax_secret" not in request.values:
        misc_logger.warning("ajax_secret absent")
        raise BadAJAXSecret
    session.require(False)
    if request.values["ajax_secret"] != session["ajax_secret"]:
        misc_logger.warning("ajax_secret bad")
        raise BadAJAXSecret

def requires_ajax(view_function):
    """Decorator that calls :meth:`check_ajax` before the view function"""

    def wrapper(*args, **kwargs):
        check_ajax()
        return view_function(*args, **kwargs)

    functools.update_wrapper(wrapper, view_function)
    return wrapper

class MatriculationImplausible(ValueError, werkzeug.exceptions.BadRequest):
    """The matriculation year is too far in the past."""

class MatriculationTimetravel(MatriculationImplausible):
    """The matriculation year is in the future."""

def parse_matriculation_year(value):
    """Attempt to parse a 2 or 4 digit year"""
    value = value.strip()

    # only do two digit stuff with "01", not "1"
    twodigit = len(value) == 2
    value = int(value)

    if twodigit and 30 < value <= 99:
        value = 1900 + value
    elif twodigit and 0 <= value <= 30:
        value = 2000 + value

    if value > datetime.datetime.utcnow().year:
        future = True
        raise MatriculationTimetravel
    elif value < 1900:
        raise MatriculationImplausible
    else:
        return value
