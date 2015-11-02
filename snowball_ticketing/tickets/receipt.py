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

"""receipt - email receipt sending functions"""

from __future__ import unicode_literals

from datetime import datetime, timedelta
import psycopg2

from .. import tickets, utils, users, queries


__all__ = ["update_all", "needs_update", "send_update"]


logger = utils.getLogger(__name__)


def receipts_main(postgres_settings):
    """Setup a connection and run :func:`update_all`"""
    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            **postgres_settings)
    try:
        update_all(conn)
    except Exception:
        logger.exception("Unhandled receipt exception")

def update_all(pg):
    """Send receipt emails to everyone that :func:`needs_update`"""
    for user_id in needs_update(pg):
        send_update(user_id, pg)

def needs_update(pg):
    """
    Yields a list of user_ids that need a receipt email

    "Need" = something has been finalised or paid for since their last
    receipt, and they don't have unfinalised tickets that are shortly going
    to expire.

    Doesn't hold the transaction open while yielding.
    """

    with pg.cursor() as cur:
        cur.execute(queries.needs_receipt)
        rows = cur.fetchall()

    # don't hold the transaction open!
    pg.commit()

    logger.debug("needs_update: %s", len(rows))

    for user_id, last_receipt, updated in rows:
        logger.debug("User %s needs update (%s < %s)",
                    user_id, last_receipt, updated,
                    extra={"user_id": user_id})
        yield user_id

def send_update(user_id, pg, ask_pay_within=7,
                harass=False, deadline=None, waiting_release=False):
    """
    Send a receipt email to `user_id`.

    Includes the payment-harassment paragraph if `harass` is ``True`` with
    the `deadline` specified, and the waiting-list-successful paragraph if
    `waiting_release` is true.

    `ask_pay_within` sets the "we ask that you complete payment within"
    "days".
    """

    assert not (harass and waiting_release)
    assert harass == (deadline is not None)

    tickets.user_pg_lock(user_id, pg=pg)

    user = users.get_user(user_id, pg=pg)

    paid_tickets = []
    unpaid_tickets = []
    waiting_list_places = 0
    updated = None

    for ticket in tickets.tickets(user_id=user_id, finalised=True, pg=pg):
        updated = _none_max(updated, ticket["finalised"])
        updated = _none_max(updated, ticket["paid"])

        if ticket["waiting_list"]:
            waiting_list_places += 1
        elif ticket["paid"] is not None:
            paid_tickets.append(ticket)
        else:
            unpaid_tickets.append(ticket)

    assert updated is not None

    def k(t): return (t["othernames"], t["surname"])
    paid_tickets.sort(key=k)
    unpaid_tickets.sort(key=k)

    outstanding_balance = tickets.outstanding_balance(user_id, pg=pg)

    if harass:
        mail_type = "harassment"
        assert unpaid_tickets
    elif waiting_release:
        mail_type = "waiting release"
        assert unpaid_tickets
    else:
        mail_type = "receipt"

    logger.info("Sending %s mail to user %s; "
                "last_receipt %s, updated %s; "
                "paid tickets %r, unpaid tickets %r, wl places %s, "
                "harass deadline %s, outstanding balance %s, "
                "ask pay within %s",
                mail_type, user["user_id"], user["last_receipt"], updated,
                [t["ticket_id"] for t in paid_tickets],
                [t["ticket_id"] for t in unpaid_tickets],
                waiting_list_places,
                deadline if harass else None,
                outstanding_balance, ask_pay_within,
                extra={"user_id": user_id})

    if user["othernames"] is not None and user["surname"] is not None:
        name = user["othernames"] + " " + user["surname"]
    else:
        name = None

    with pg.cursor() as cur:
        cur.execute("UPDATE users SET last_receipt = %s "
                    "WHERE user_id = %s",
                    (updated, user_id))

    # don't hold the locks or the transaction!
    pg.commit()

    utils.send_email("receipt.txt", recipient=(name, user["email"]),
                     sender=("Snowball Ticketing",
                             "webmaster@selwynsnowball.co.uk"),
                     harass=harass,
                     waiting_release=waiting_release,
                     payment_deadline=deadline,
                     paid_tickets=paid_tickets,
                     unpaid_tickets=unpaid_tickets,
                     waiting_list_places=waiting_list_places,
                     payment_reference=tickets.reference(user),
                     outstanding_balance=outstanding_balance,
                     ask_pay_within=ask_pay_within)

def _none_max(a, b):
    """Return ``max(a, b)``, treating None as ``-infinity``"""
    if a is None:
        return b
    elif b is None:
        return a
    else:
        return max(a, b)
