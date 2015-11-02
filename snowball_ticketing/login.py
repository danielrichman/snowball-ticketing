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

"""The login (and associated tasks) views"""

from __future__ import unicode_literals

import re
from datetime import datetime

import flask
import jinja2
import werkzeug.exceptions
import psycopg2.extensions
import ucam_webauth
import raven
from flask import request, redirect, render_template, url_for, abort, session

from . import utils, lookup, users, tickets
from .utils import postgres


__all__ = ["bp", "index", "logout", "raven_login", "raven_response",
           "raven_error", "password_signup", "password_login",
           "password_forgotten", "email_confirm", "email_reset", "login_next",
           "user_details", "email_confirm_resend", "user_disabled_response"]

logger = utils.getLogger(__name__)

# should match the regex from the constraint in schema.sql
email_regex = re.compile(r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,4}$')


#: the :class:`flask.Blueprint` containing login views.
bp = flask.Blueprint('login', __name__)


@bp.route("/login", defaults={"section": "login-choices"})
@bp.route("/password", defaults={"section": "password-choices"})
@bp.route("/password/login", defaults={"section": "password-login"})
@bp.route("/password/signup", defaults={"section": "password-signup"})
@bp.route("/password/forgotten", defaults={"section": "password-forgotten"})
def index(section):
    if session.ok:
        return redirect(login_next())
    else:
        return render_template("login/main-history.html", section=section,
                               tickets_mode_sentence=tickets.mode_sentence())

@bp.route("/logout", methods=["POST"])
def logout():
    if session.ok:
        utils.check_csrf()
        session.destroy()
    return redirect(url_for("info.index"))

@bp.route("/raven/login")
def raven_login():
    request = raven.Request(url=url_for(".raven_response", _external=True),
                            desc="Selwyn Snowball Ticketing")
    return redirect(unicode(request))

@bp.route("/raven/response")
def raven_response():
    if session.ok:
        session.destroy()

    try:
        r = raven.Response(request.args["WLS-Response"])
    except ValueError as e:
        logger.warning("Invalid raven response: %s", e)
        abort(400)

    if r.url != url_for(".raven_response", _external=True):
        logger.warning("Invalid raven response: bad url")
        abort(400)

    issue_delta = (datetime.utcnow() - r.issue).total_seconds()
    if not -5 < issue_delta < 15:
        logger.warning("Invalid raven response: bad issue")
        return redirect(url_for(".raven_error", reason="error"))

    if not r.success:
        if r.status == ucam_webauth.STATUS_CANCELLED:
            return redirect(url_for(".raven_error", reason="cancelled"))
        else:
            return redirect(url_for(".raven_error", reason="error"))

    if "current" not in r.ptags:
        return redirect(url_for(".raven_error", reason="alumni"))

    user = users.get_raven_user(r.principal)

    if user is None:
        # end the transaction: it's safe to do so, and the lookup
        # operation is slow
        postgres.commit()

        try:
            lookup_data = lookup.get_crsid(r.principal)
        except lookup.LookupFailed:
            # lookup logs its own errors
            lookup_data = {}

        # This could happen, I guess...
        if lookup_data.get("person_type") == "alumnus":
            logger.warning("%s has current ptag but lookup yielded "
                           "person_type=alumnus", r.principal)
            return redirect(url_for(".raven_error", reason="alumni"))

        # ensure that the .rollback() in except: doesn't destroy anything
        # (if we couldn't end the transaction above we could use savepoints)
        assert postgres.connection.get_transaction_status() == \
                psycopg2.extensions.TRANSACTION_STATUS_IDLE

        try:
            user = users.new_raven_user(r.principal, r.ptags, lookup_data)
        except users.CRSIDAlreadyExists:
            logger.warning("Raced with another request to create Raven user "
                           "for crsid %s", r.principal)
            postgres.connection.rollback()

            user = users.get_raven_user(r.principal)
            assert user is not None

    # for a disabled password user, we reject it during authentication
    # (in users.password_login). For Raven, we'll have to do it here.
    if not user["enable_login"]:
        return redirect(url_for(".raven_error", reason="disabled"))

    logger.info("logging in user %s (via Raven %s)",
                user["user_id"], r.principal)

    session.create(user)
    return redirect(login_next())

@bp.route("/raven/cancelled", defaults={"reason": "cancelled"})
@bp.route("/raven/error", defaults={"reason": "error"})
@bp.route("/raven/error/alumni", defaults={"reason": "alumni"})
@bp.route("/raven/error/disabled", defaults={"reason": "disabled"})
def raven_error(reason):
    if reason == "disabled":
        return user_disabled_response()

    retry = {"text": "Retry Raven Login?", "url": url_for(".raven_login")}

    if reason == "cancelled":
        page_title = "Raven Login Cancelled"
        message = "The Raven Login was cancelled."
        action = retry

    elif reason == "error":
        page_title = "Raven Login Failed"
        message = "There was an unexpected error logging into Raven."
        action = retry

    elif reason == "alumni":
        page_title = "Raven Login Failed: Alumni"
        message = "Raven login for alumni is not yet implemented, sorry."
        action = {"text": "Create a user with your email & password",
                  "url": url_for(".password_signup")}

    else:
        abort(404)

    return render_template("error.html", action=action,
                           page_title=page_title, message=message)

@bp.route("/password/signup", methods=["POST"])
def password_signup():
    if session.ok:
        session.destroy()

    email = request.form["email"].lower()
    email_again = request.form["email_again"].lower()
    password = request.form["password"]
    password_again = request.form["password_again"]

    errors = {}
    if email.endswith("@cam.ac.uk"):
        email_again = ""
        errors["should_use_raven"] = True
    elif not email_regex.match(email):
        email_again = ""
        errors["email_invalid"] = True
    elif email != email_again:
        email_again = ""
        errors["email_again_bad"] = True

    if len(password) < 8:
        errors["password_short"] = True
    elif password != password_again:
        errors["password_again_bad"] = True

    if not errors:
        with utils.with_savepoint("email_unique") as rollback:
            try:
                # the link advertises password signup as for alumni
                user = users.new_password_user(email, password, 'alumnus')
            except users.EmailAlreadyExists:
                rollback()
                errors["email_already_exists"] = True
            except users.ShouldUseRaven:
                errors["should_use_raven"] = True

    if errors:
        return render_template("login/password-signup.html",
                               email=email, email_again=email_again, **errors)
    else:
        session.create(user)
        return redirect(login_next())

@bp.route("/password/login", methods=["POST"])
def password_login():
    if session.ok:
        session.destroy()

    email = request.form["email"].lower()
    password = request.form["password"]

    try:
        user = users.password_login("email", email, password)
    except users.ShouldUseRaven:
        return render_template("login/password-login.html",
                               should_use_raven=True, email=email)
    except users.EmailNotFound:
        return render_template("login/password-login.html",
                               bad_email=True, email=email)
    except users.BadPassword:
        return render_template("login/password-login.html",
                               bad_password=True, email=email)
    except users.UserDisabled:
        return user_disabled_response()
    else:
        logger.info("logging in user %s (via password; email %s)",
                    user["user_id"], email)

        session.create(user)
        return redirect(login_next())

@bp.route("/password/forgotten", methods=["POST"])
def password_forgotten():
    if session.ok:
        session.destroy()

    email = request.form["email"].lower()

    try:
        users.reset_password_begin(email)
    except users.ShouldUseRaven:
        return render_template("login/password-forgotten.html",
                               should_use_raven=True, email=email)
    except users.EmailNotFound:
        return render_template("login/password-forgotten.html",
                               bad_email=True, email=email)
    except users.UserDisabled:
        return user_disabled_response()
    else:
        return render_template("login/password-forgotten-success.html",
                               email=email)

@bp.route("/e/c/<int:user_id>/<secret>", methods=["GET", "POST"])
def email_confirm(user_id, secret):
    if session.ok and user_id != session["user"]["user_id"]:
        session.destroy()

    try:
        users.email_confirm_check(user_id, secret,
                                  session["user"] if session.ok else None)
    except users.EmailAlreadyConfirmed:
        return render_template("login/email-confirm.html",
                               already_confirmed=True, next=login_next())
    except users.BadSecret:
        return render_template("login/email-confirm.html", bad_secret=True)

    if not session.ok and request.method == "POST":
        password = request.form["password"]
        try:
            user = users.password_login("user_id", user_id, password)
        except users.BadPassword:
            return render_template("login/email-confirm.html",
                                   unauthenticated=True, bad_password=True,
                                   user_id=user_id, secret=secret)
        else:
            logger.info("logging in user %s (during email confirmation)",
                        user["user_id"])
            session.create(user)

    if not session.ok:
        return render_template("login/email-confirm.html",
                               unauthenticated=True,
                               user_id=user_id, secret=secret)

    users.email_confirm(user_id)
    return render_template("login/email-confirm.html",
                           confirmed=True, next=login_next())

@bp.route("/e/r/<int:user_id>/<secret>", methods=["GET", "POST"])
def email_reset(user_id, secret):
    if session.ok:
        session.destroy()

    # technically we could race between checking and resetting, allowing
    # a user to reset their password twice, but that achieves nothing

    try:
        user = users.reset_password_check(user_id, secret)
    except users.BadSecret:
        logger.warning("bad email_reset link (user %s)", user_id)
        return render_template("login/email-reset.html", invalid=True)

    if request.method == "GET":
        return render_template("login/email-reset.html", ready=True,
                               user_id=user_id, secret=secret,
                               email=user["email"])

    else:
        password = request.form["password"]
        password_again = request.form["password_again"]
        errors = {}

        if len(password) < 8:
            errors["password_short"] = True
        elif password != password_again:
            errors["password_again_bad"] = True

        if errors:
            return render_template("login/email-reset.html",
                                   user_id=user_id, secret=secret,
                                   email=user["email"],
                                   change_failed=True, **errors)

        else:
            users.reset_password(user_id, password)
            if not user["email_confirmed"]:
                # user arrived here via a link in an email, and is logged in
                users.email_confirm(user_id)
            session.create(user)

            return render_template("login/email-reset.html",
                                   success=True, next=login_next())

def login_next():
    if session["user"]["details_completed"]:
        return url_for("tickets.home")
    else:
        return url_for(".user_details")

@bp.route("/user_details", methods=["GET", "POST"])
def user_details():
    session.require(False)
    utils.check_csrf()

    user = session["user"]
    if user["details_completed"]:
        return redirect(login_next())

    def nonevalue(v): return v if v is not None else ""

    # final: don't allow modifications to values already in db

    details_ok = True
    data = ("person_type", "crsid", "email", "email_confirmed")
    strings = ("surname", "othernames")
    update = {}
    kwargs = {}

    # person_type, crsid, email
    for key in data:
        kwargs[key] = user[key]

    # surname, othernames
    for key in strings:
        final = user[key] is not None
        empty_error = False

        if not final and key in request.form:
            value = request.form[key].strip()
            if value == "":
                value = None
        else:
            value = user[key]

        if value is None:
            details_ok = False
            empty_error = True

        elif value != user[key]:
            update[key] = value
            final = True

        kwargs[key] = {"value": nonevalue(value), "final": final,
                       "error": empty_error, "empty": empty_error}

    # college_id
    final = user["college_id"] is not None
    empty_error = False

    if not final and "college_id" in request.form:
        value = request.form["college_id"]
        if value != "":
            try:
                value = int(value)
            except ValueError:
                abort(400)
            if value not in utils.all_colleges():
                abort(400)
        else:
            value = None
    else:
        value = user["college_id"]

    if value is None:
        details_ok = False
        empty_error = True

    elif value != user["college_id"]:
        update["college_id"] = value
        final = True

    kwargs["college_id"] = {"value": value, "final": final,
                            "error": empty_error, "empty": empty_error}

    # matriculation_year
    if user["person_type"] == "alumnus":
        final = user["matriculation_year"] is not None
        invalid = empty = future = False

        if not final and "matriculation_year" in request.form:
            value = request.form["matriculation_year"].strip()
            if value != "":
                try:
                    value = utils.parse_matriculation_year(value)
                except utils.MatriculationTimetravel:
                    future = True
                except ValueError:
                    invalid = True
            else:
                value = None
        else:
            value = user["matriculation_year"]

        if not invalid and value is None:
            empty = True

        if empty or future or invalid:
            details_ok = False
        elif value != user["matriculation_year"]:
            update["matriculation_year"] = value
            final = True

        kwargs["matriculation_year"] = \
                {"value": nonevalue(value), "final": final, "empty": empty,
                 "future": future, "invalid": invalid,
                 "error": empty or future or invalid,
                 "hide": False}

    else:
        kwargs["matriculation_year"] = {"hide": True}

    # update logic
    if update:
        logger.info("User %s provided updates for keys %s",
                    user["user_id"], ', '.join(update))

    if not details_ok:
        error_keys = []

        for key, value in kwargs.iteritems():
            if isinstance(value, dict) and value.get("error"):
                error_keys.append(key)

        if request.method != "POST":
            # show neither empty text nor scary redness on the GET request
            for key in error_keys:
                kwargs[key]["error"] = False
                kwargs[key]["empty"] = False

        else:
            logger.info("Errors in user provided updates for keys %s",
                        ', '.join(error_keys))

    if details_ok and not user["email_confirmed"]:
        kwargs["need_email_only"] = True
        details_ok = False
    else:
        kwargs["need_email_only"] = False

    if details_ok and request.method == "POST":
        update["details_completed"] = True

    if update:
        users.update_user(user["user_id"], **update)
        # `user` was grabbed from flask.session by reference, and
        # update_user() update()s that dict

    if user["details_completed"]:
        return redirect(login_next())
    else:
        return render_template("login/user-details.html", **kwargs)

@bp.route("/user_details/resend_confirm", methods=["POST"])
def email_confirm_resend():
    session.require(False)
    utils.check_ajax()

    try:
        users.email_confirm_send(session["user_id"])
    except users.EmailAlreadyConfirmed:
        logger.warning("email was already confirmed when resending (ajax)")
        r = "ALREADY CONFIRMED"
    else:
        r = "OK"

    return flask.Response(r, mimetype="text/plain")

def user_disabled_response():
    # used by raven_response, password_login, password_forgotten
    return render_template("error.html", page_title="Account Disabled",
                           message="Sorry - this user has been disabled.")
