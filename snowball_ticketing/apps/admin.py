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

"""dashboard app"""

from __future__ import unicode_literals

import os
from datetime import timedelta
 
import pytz
from flask import Flask, render_template
from raven.flask_glue import AuthDecorator

from .. import utils, tickets, queries
 
app = Flask(__name__,
            static_folder='../../static',
            template_folder='../../templates')

# this is lazy. Also requires there to be only one gunicorn worker
# (which there is)
app.secret_key = os.urandom(16)

utils.PostgreSQL(app)

users = frozenset({"djr61"})

auth_decorator = AuthDecorator(require_principal=users,
                               can_trust_request_host=True)
app.before_request(auth_decorator.before_request)
 
@app.route("/admin/dashboard")
def dashboard():
    quotas = {}
    for (who, what), settings in tickets.settings().items():
        quotas["{0}_{1}".format(who, what)] = settings["quota"]
        quotas["waiting_{0}_{1}".format(who, what)] = settings["waiting_quota"]

    with utils.postgres.cursor(True) as cur:
        cur.execute(queries.paid_counts)
        paid = cur.fetchone()

    return render_template("admin/dashboard.html",
                           quotas=quotas,
                           counts=tickets.counts(),
                           paid=paid,
                           histogram=list(_tickets_histogram()))

def _tickets_histogram():
    query = "SELECT date_trunc('hour', created) AS hour_bin, count(*) " \
            "FROM tickets WHERE finalised IS NOT NULL AND NOT waiting_list " \
            "GROUP BY hour_bin ORDER BY hour_bin"

    hour = timedelta(hours=1)

    pytz_bst = pytz.timezone("Europe/London")
    def tuplify(dt):
        dt = dt.replace(tzinfo=pytz.utc).astimezone(pytz_bst)
        return dt.utctimetuple()[:4]

    with utils.postgres.cursor() as cur:
        cur.execute(query)

        hour_bin, count = cur.fetchone()
        yield tuplify(hour_bin), count

        while True:
            row = cur.fetchone()
            if row is None:
                return

            next_hour_bin, count = row
            while hour_bin < next_hour_bin - hour:
                hour_bin += hour
                yield tuplify(hour_bin), 0
            hour_bin = next_hour_bin

            yield tuplify(hour_bin), count
