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

"""snowball ticketing system"""

from __future__ import unicode_literals

import logging
import time

import flask
from flask import Flask, redirect, render_template, url_for, jsonify
from flask import request, Response

from .. import utils, login, info
from ..tickets import views as tickets_views


app = Flask(__name__,
            static_folder='../../static',
            template_folder='../../templates')

app.session_interface = utils.SessionInterface()
app.config["SESSION_COOKIE_NAME"] = "snowball_ticketing"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True

utils.customise_jinja(app)
utils.PostgreSQL(app)
app.register_blueprint(info.bp)
app.register_blueprint(login.bp)
app.register_blueprint(tickets_views.bp)


@app.after_request
def add_no_cache(response):
    if request.endpoint != "static":
        response.headers[b"Cache-Control"] = "no-cache"
        response.headers[b"Pragma"] = "no-cache"
    return response


@app.route("/time", endpoint="time")
def time_view():
    # this view is cached by my browser specifically needs to not be.
    # The decorator above might change, but this must not.
    response = jsonify({"time": int(time.time())})
    response.headers[b"Cache-Control"] = "no-cache"
    response.headers[b"Pragma"] = "no-cache"
    return response

@app.route("/heartbeat")
def heartbeat():
    with utils.postgres.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchall() == [(1,)]
    return Response("OK", mimetype='text/plain')

@app.errorhandler(utils.SessionAbsent)
def session_absent(e):
    login_url = url_for("login.index", section="login-choices")
    return render_template("error.html", page_title="Log in required",
                           message="You must be logged in to do that",
                           action={"text": "Log in", "url": login_url})

@app.errorhandler(utils.SessionExpired)
def session_expired(e):
    login_url = url_for("login.index", section="login-choices")
    return render_template("error.html", page_title="Session expired",
                           message="Your last action was more than a day ago "
                                   "and as a consequence your session has "
                                   "expired. Please login again.",
                           action={"text": "Log in", "url": login_url})

@app.errorhandler(utils.SessionUserDetailsIncomplete)
def session_user_details_incomplete(e):
    return redirect(url_for("login.user_details"))

@app.errorhandler(utils.SessionUserDisabled)
def session_user_disabled(e):
    return login.user_disabled_response()

# This handler must be added last, since the others are subclasses.
app.register_error_handler(utils.SessionInvalid, session_absent)
