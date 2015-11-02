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

"""Miscellaneous functions that interact with the `users` table"""

from datetime import datetime, timedelta

import flask
import werkzeug.exceptions
from werkzeug.security import safe_str_cmp
import bcrypt
import psycopg2
import psycopg2.errorcodes

from . import utils


__all__ = ["ShouldUseRaven", "CRSIDAlreadyExists", "EmailAlreadyExists",
           "EmailAlreadyConfirmed", "BadSecret", "EmailNotFound",
           "BadPassword", "WrongUserType", "UserDisabled",
           "get_raven_user", "new_raven_user",
           "new_password_user", "password_login",
           "email_confirm_send", "email_confirm_check", "email_confirm",
           "reset_password_begin", "reset_password_check", "reset_password",
           "change_password", "update_user", "get_user"]


logger = utils.getLogger(__name__)


class ShouldUseRaven(Exception):
    """The user should use Raven to perform, or instead of, this operation"""

class CRSIDAlreadyExists(Exception):
    """A user for this CRSID already exists"""

class EmailAlreadyExists(Exception):
    """A user with this email address already exists"""

class EmailAlreadyConfirmed(Exception):
    """The email address was already confirmed"""

class BadSecret(werkzeug.exceptions.NotFound):
    """Secret value (for email confirmation or password reset) was bad"""

class EmailNotFound(Exception):
    """Email address not found in users table"""

class BadPassword(Exception):
    """Incorrect password"""

class WrongUserType(Exception):
    """Wrong user_type for requested operation"""
    def __init__(self, got=None, expected=None):
        self.got = got
        self.expected = expected
    def __str__(self):
        s = ""
        if self.got is not None and self.expected is not None:
            return "expected {0} got {1}".format(self.expected, self.got)
        elif self.got is not None:
            return self.got
        elif self.expected is not None:
            return "expected {0}".format(self.expected)
        else:
            return ""

class UserDisabled(werkzeug.exceptions.Forbidden):
    """User is disabled (``enable_login == False``)"""


def get_raven_user(crsid, pg=utils.postgres):
    """Finds a user by CRSID, returning ``None`` if it doesn't exist"""

    # the schema guarantees that if crsid is set they are a raven user
    query = "SELECT * FROM users WHERE crsid = %s"

    with pg.cursor(True) as cur:
        cur.execute(query, (crsid.lower(), ))
        assert cur.rowcount in (0, 1)
        if cur.rowcount == 1:
            user = cur.fetchone()
            if user["user_type"] != 'raven':
                raise WrongUserType(user["user_type"], 'raven')
            return user
        else:
            return None

def new_raven_user(principal, ptags, lookup_data, pg=utils.postgres):
    """
    Create a user row for a Raven principal

    The user must not be an alumnus!

    Some fields are pre-filled with data from lookup.

    Raises :exc:`CRSIDAlreadyExists` if ... a user with this crsid already
    exists. Note that postgres throwing a UNIQUE violation will abort the
    current transaction.

    The created user is returned
    """

    assert len(principal)
    assert "current" in ptags
    assert lookup_data.get("person_type") != "alumnus"

    details = lookup_data.copy()
    principal = principal.lower()
    details["crsid"] = principal
    details["email"] = details["crsid"] + "@cam.ac.uk"

    details.setdefault("othernames", None)
    details.setdefault("surname", None)
    details.setdefault("person_type", "cam-other")

    query1 = "SELECT college_id FROM colleges WHERE instid = %s"
    query2 = "INSERT INTO users " \
             "(user_type, surname, othernames, person_type, " \
                 "college_id, crsid, email, email_confirmed, " \
                 "enable_login, details_from_lookup)" \
             "VALUES " \
             "('raven', %(surname)s, %(othernames)s, %(person_type)s, " \
                 "%(college_id)s, %(crsid)s, %(email)s, TRUE, " \
                 "TRUE, %(details_from_lookup)s) " \
             "RETURNING *"

    with pg.cursor(True) as cur:
        if "college_instid" in details:
            cur.execute(query1, (details["college_instid"], ))
            if cur.rowcount == 1:
                details["college_id"] = cur.fetchone()["college_id"]
            else:
                logger.warning("college instid %s from lookup not found",
                               details["college_instid"])

        details.setdefault("college_id", None)

        details["details_from_lookup"] = \
            details["surname"] is not None and \
            details["college_id"] is not None and \
            details["person_type"] is not None

        try:
            cur.execute(query2, details)
        except psycopg2.IntegrityError as e:
            if e.pgcode == psycopg2.errorcodes.UNIQUE_VIOLATION:
                # crsid unique - another request won the race
                # constraints guarantee that for users with crsid set
                # the email is always crsid@cam.ac.uk, and users with
                # crsid unset can't have email addresses ending @cam.ac.uk,
                # ensuring we don't run into email unique problems
                raise CRSIDAlreadyExists(principal)
            else:
                raise
        else:
            assert cur.rowcount == 1
            user = cur.fetchone()
            logger.info("Created user %s (%s %s) for (Raven) %s, %r",
                        user["user_id"], details.get("college_instid", None),
                        user["person_type"], principal, ','.join(ptags))
            return user

def new_password_user(email, password, person_type, pg=utils.postgres):
    """
    Create a new password-login user with `email` and `password`

    Raises :exc:`ShouldUseRaven` in response to cam email addresses.

    If a user already exists with that email address,
    :exc:`EmailAlreadyExists` is raised. Note that postgres throwing a
    UNIQUE violation will abort the current transaction.

    Returns the new user.
    """

    email = email.lower()
    if email.endswith("@cam.ac.uk"):
        raise ShouldUseRaven(email)

    hashed = bcrypt.hashpw(password, bcrypt.gensalt(10))

    query = "INSERT INTO users " \
            "(user_type, person_type, email, password_bcrypt, enable_login)" \
            "VALUES ('password', %s, %s, %s, TRUE) " \
            "RETURNING *"

    with pg.cursor(True) as cur:
        try:
            cur.execute(query, (person_type, email, hashed))
        except psycopg2.IntegrityError as e:
            if e.pgcode == psycopg2.errorcodes.UNIQUE_VIOLATION:
                logger.warning("new password user failed - "
                               "user for email %s already existed ",
                               email)
                raise EmailAlreadyExists(email)
            else:
                raise
        else:
            assert cur.rowcount == 1
            user = cur.fetchone()
            logger.info("created password login user %s for email %s",
                        user["user_id"], email)

            email_confirm_send(user["user_id"], update_user=user, pg=pg)
            return user

def password_login(id_type, identifier, password, pg=utils.postgres):
    """
    Attempts to log in using (`identifier`, `password`)

    `id_type` must be either 'user_id' or 'email'

    Returns the user, or raises one of :exc:`ShouldUseRaven`, 
    :exc:`EmailNotFound`, :exc:`BadPassword` or :exc:`UserDisabled`.
    """

    assert id_type in ("user_id", "email")

    # the schema guarantees us that raven users only have cam emails
    if id_type == "email":
        identifier = identifier.lower()
        if identifier.endswith("@cam.ac.uk"):
            raise ShouldUseRaven(identifier)

    query = "SELECT * FROM users WHERE {0} = %s".format(id_type)

    with pg.cursor(True) as cur:
        cur.execute(query, (identifier, ))
        assert cur.rowcount in (0, 1)
        if cur.rowcount == 1:
            user = cur.fetchone()
        else:
            assert id_type != "user_id" # this shouldn't happen
            logger.info("password login failed - bad %s %r",
                        id_type, identifier)
            raise EmailNotFound(identifier)

    if user["user_type"] == 'raven':
        logger.warning("password login attempted on raven user %s (%s)",
                       user["crsid"], user["user_id"])
        raise ShouldUseRaven(user["email"])
    elif user["user_type"] != 'password':
        logger.warning("password login attempted on non password user %s",
                       user["user_id"])
        raise WrongUserType(user["user_type"], 'password')

    if not user["enable_login"]:
        logger.warning("password login attempted while disabled - "
                       "user %s", user["user_id"])
        raise UserDisabled(user["user_id"])

    compare = bcrypt.hashpw(password, user["password_bcrypt"])
    if safe_str_cmp(user["password_bcrypt"], compare):
        logger.info("good password for user %s", user["user_id"])
        return user
    else:
        logger.info("bad password for user %s", user["user_id"])
        raise BadPassword(user["user_id"])

def email_confirm_send(user_id, update_user=None, pg=utils.postgres):
    """
    Send an email to confirm that a user owns the email they claim to.

    If `update_user` is provided, the dict is updated with the new
    `email_confirm_secret`, if one is generated.

    Raises :exc:`EmailAlreadyConfirmed` if appropriate.
    """

    # since we're specifying the user using `user_id`, assume they exist.

    query1 = "UPDATE users " \
             "SET email_confirm_secret = %s " \
             "WHERE email_confirm_secret IS NULL AND " \
                "user_id = %s AND NOT email_confirmed"

    query2 = "SELECT othernames, surname, email, email_confirm_secret " \
             "FROM users WHERE user_id = %s AND NOT email_confirmed"

    with pg.cursor() as cur:
        cur.execute(query1, (utils.gen_secret(), user_id))
        assert cur.rowcount in (0, 1)
        new_secret = bool(cur.rowcount)

        cur.execute(query2, (user_id, ))
        assert cur.rowcount in (0, 1)

        if cur.rowcount == 0:
            raise EmailAlreadyConfirmed(user_id)

        othernames, surname, email, email_confirm_secret = cur.fetchone()

    if othernames is not None and surname is not None:
        name = othernames + " " + surname
    else:
        name = None

    utils.send_email("confirm.txt", recipient=(name, email),
                     sender=("Snowball Ticketing",
                             "webmaster@selwynsnowball.co.uk"),
                     user_id=user_id,
                     secret=email_confirm_secret)

    if new_secret:
        u = {"email_confirm_secret": email_confirm_secret}
        _update_session(user_id, u)
        if update_user is not None:
            update_user.update(u)

        first = "(the initial)"
    else:
        first = "(another)"

    logger.info("sent %s confirmation email for user %s to %s",
                first, user_id, email)

def email_confirm_check(user_id, secret, user=None, pg=utils.postgres):
    """
    Checks an email confirm link
    
    Returns ``False`` if it was already confirmed, ``True`` if the link is OK,
    and raises :class:`BadSecret` otherwise.

    If `user` is provided it is used instead of querying the database.
    """

    query = "SELECT email_confirm_secret, email_confirmed " \
            "FROM users WHERE user_id = %s"

    if user is None:
        with pg.cursor(True) as cur:
            cur.execute(query, (user_id, ))
            assert cur.rowcount in (0, 1)
            if cur.rowcount == 1:
                user = cur.fetchone()
            else:
                logger.warning("bad user_id %s (in email confirm)", user_id)
                raise BadSecret
    else:
        assert user_id == user["user_id"]

    if user["email_confirmed"]:
        raise EmailAlreadyConfirmed(user_id)

    if user["email_confirm_secret"] == secret:
        return True
    else:
        raise BadSecret

def email_confirm(user_id, pg=utils.postgres):
    """Mark an email address as confirmed"""

    update_user(user_id, email_confirmed=True, pg=pg)
    logger.info("confirmed email address for user %s", user_id)

def reset_password_begin(email, pg=utils.postgres):
    """
    Start the password reset process for the user with email `email`

    Raises :exc:`ShouldUseRaven` or :exc:`EmailNotFound` if appropriate.
    """

    email = email.lower()

    # reset_password_begin does not update flask.session["user"] - this will
    # need to be implemented if you start calling it with the user logged in
    # (which doesn't make sense anyway?)
    assert not (flask.current_app and flask.session.ok and
                flask.session["user"]["email"] == email)

    if email.endswith("@cam.ac.uk"):
        raise ShouldUseRaven(email)

    valid_cond = "(pwreset_expires IS NULL OR pwreset_expires < utcnow())"

    query1 = "SELECT *, {cond} AS pwreset_invalid " \
             "FROM users " \
             "WHERE email = %s" \
                .format(cond=valid_cond)

    # check the condition again in case of races.
    query2 = "UPDATE users " \
             "SET pwreset_secret = %s, pwreset_created = utcnow(), " \
                 "pwreset_expires = utcnow() + '3 days'::interval " \
             "WHERE user_id = %s AND {cond} " \
             "RETURNING pwreset_secret, pwreset_created, pwreset_expires" \
                .format(cond=valid_cond)

    query3 = "SELECT pwreset_secret, pwreset_created, pwreset_expires " \
             "FROM users WHERE user_id = %s"

    query4 = "UPDATE users " \
             "SET pwreset_expires = utcnow() + '3 days'::interval " \
             "WHERE user_id = %s " \
             "RETURNING pwreset_expires"

    with pg.cursor(True) as cur:
        cur.execute(query1, (email, ))
        assert cur.rowcount in (0, 1)
        if cur.rowcount == 0:
            raise EmailNotFound(email)

        user = cur.fetchone()

        if not user["enable_login"]:
            raise UserDisabled(user["user_id"])

        if user["user_type"] == 'raven':
            raise ShouldUseRaven(email)
        elif user["user_type"] != 'password':
            raise WrongUserType(user["user_type"], 'password')

        msg = "extended pwreset_expires"

        if user["pwreset_invalid"]:
            cur.execute(query2, (utils.gen_secret(), user["user_id"], ))
            assert cur.rowcount in (0, 1)
            if cur.rowcount == 1:
                msg = "new pwreset_secret"
                user.update(cur.fetchone())
            else:
                logger.warning("Raced to set pwreset_secret for user %s",
                               user["user_id"])
                msg = "new pwreset_secret (race)"
                cur.execute(query3, (user["user_id"], ))
                assert cur.rowcount == 1
                user.update(cur.fetchone())
        else:
            msg = "extended pwreset_expires"
            cur.execute(query4, (user["user_id"], ))
            assert cur.rowcount == 1
            user.update(cur.fetchone())

        if user["othernames"] is not None and user["surname"] is not None:
            name = "{othernames} {surname}".format(**user)
        else:
            name = None

        logger.info("%s for user %s (email %s)",
                    msg, user["user_id"], email)

        utils.send_email("password-reset.txt", recipient=(name, email),
                         sender=("Snowball Ticketing",
                                 "webmaster@selwynsnowball.co.uk"),
                         user_id=user["user_id"],
                         expires=user["pwreset_expires"],
                         secret=user["pwreset_secret"])

def reset_password_check(user_id, secret, pg=utils.postgres):
    """
    Check the password reset secret
    
    Either returns the user, or raises :exc:`BadSecret`.
    """

    query = "SELECT * FROM users " \
            "WHERE user_id = %s AND pwreset_secret = %s AND " \
                "pwreset_expires > utcnow()"

    with pg.cursor(True) as cur:
        cur.execute(query, (user_id, secret))
        assert cur.rowcount in (0, 1)
        if cur.rowcount == 1:
            logger.info("Accepted reset password secret for user %s",
                        user_id)
            return cur.fetchone()
        else:
            raise BadSecret

def reset_password(user_id, new_password, pg=utils.postgres):
    """Change a users' password and delete pwreset_secret"""

    hashed = bcrypt.hashpw(new_password, bcrypt.gensalt(10))
    update_user(user_id, password_bcrypt=hashed, pwreset_created=None,
                         pwreset_secret=None, pwreset_expires=None, pg=pg)
    logger.info("Changed password (via pwreset) for user %s", user_id)

def change_password(user_id, new_password, pg=utils.postgres):
    """Change a users' password"""

    hashed = bcrypt.hashpw(new_password, bcrypt.gensalt(10))
    update_user(user_id, password_bcrypt=hashed, pg=pg)
    logger.info("Changed password for user %s", user_id)

def update_user(user_id, pg=utils.postgres, **kwargs):
    """
    Update user `user_id`, setting all keys in kwargs.

    e.g.,::

        update_user(1, person_type='undergraduate')

    Returns the updated user. If `user_id` matches
    ``flask.session["user_id"]``, then the session object is updated.
    """

    keys = ("user_type", "surname", "othernames", "person_type", "college_id",
            "matriculation_year", "crsid", "details_from_lookup",
            "details_completed", "email", "email_confirm_secret",
            "email_confirmed", "password_bcrypt", "pwreset_created",
            "pwreset_secret", "pwreset_expires", "enable_login",
            "hide_instructions", "notes")

    for key in kwargs:
        if key not in keys:
            raise RuntimeError("bad key")

    logger.debug("updating user %s, keys %s", user_id,
                 ', '.join(kwargs))

    items = list(kwargs.items())

    updates = ', '.join("{0} = %({0})s".format(key) for key in kwargs)
    query = "UPDATE users " \
            "SET " + updates + " " \
            "WHERE user_id = %(user_id)s " \
            "RETURNING *"

    kwargs["user_id"] = user_id

    with pg.cursor(True) as cur:
        cur.execute(query, kwargs)
        assert cur.rowcount == 1
        user = cur.fetchone()

    _update_session(user_id, user)

    return user

def _update_session(user_id, update):
    if flask.current_app and flask.session.ok and \
            flask.session["user_id"] == user_id:
        flask.session["user"].update(update)


class NoSuchUser(Exception):
    """That user_id is not associated with a user"""

def get_user(user_id, pg=utils.postgres):
    """Get a user"""
    query = "SELECT * FROM users WHERE user_id = %s"
    with pg.cursor(True) as cur:
        cur.execute(query, (user_id, ))
        if cur.rowcount != 1:
            raise NoSuchUser
        return cur.fetchone()
