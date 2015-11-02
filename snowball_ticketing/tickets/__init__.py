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

"""tickets - tickets table manipulation functions"""

from __future__ import unicode_literals

import re
from datetime import datetime

import flask
from werkzeug.datastructures import ImmutableDict

from .. import utils, queries


__all__ = ["available", "quotas_per_person_sentence", "none_min",
           "counts", "prices", "settings", "tickets",
           "BuyFailed", "InsufficientSpare", "QPPAnyMet", "QPPTypeMet",
           "FormRace", "IncorrectMode", "QuotaMet", "QuotaNotMet",
           "WaitingQuotaMet",
           "buy", "buy_lock", "user_pg_lock", "set_quota_met",
           "FinaliseRace", "AlreadyFinalised", "NonExistantTicket",
           "finalise", "outstanding_balance",
           "mark_paid", "purge_unpaid", "waiting_release"]


logger = utils.getLogger("snowball_ticketing.tickets")

buy_pg_lock_num = (0x123abc, 100)
user_pg_lock_num = 0x124000

_null_settings_row = \
    ImmutableDict({"quota": None, "quota_met": None,
                   "waiting_quota": None, "waiting_quota_met": None,
                   "waiting_smallquota": None, "quota_per_person": None,
                   "mode": 'available'})


def available(ticket_type, user_group=None, pg=utils.postgres):
    """
    Find out whether `user_group` can buy `ticket_type` tickets

    Returns a dict, with the following keys:
    
    * `mode`: one of ``not-yet-open``, ``available`` or ``closed``
    * `spare`: how many more can be bought
    * `waiting_spare`: how many can be added to the waiting list
    * `waiting_small`: Is `waiting count` < ``waiting_smallquota``?
    * `qpp_any`: The smallest ``quota_per_person`` applying to any ticket type
    * `qpp_type`: The smallest ``quota_per_person`` applying to this ticket type

    The last five keys may be ``None``, corresponding to "no limit".
    """

    if user_group is None:
        user_group = _user_group_from_user(flask.session["user"])

    s = settings(pg=pg)
    c = counts(pg=pg)

    result = {}

    overall_mode = 'available'
    overall_spare = None
    overall_quota_met = None
    overall_waiting_spare = None
    overall_waiting_quota_met = None
    overall_qpp_type = None
    overall_qpp_any = None
    waiting_small = None

    for test in _test_keys(user_group, ticket_type):
        limits = s.get(test, _null_settings_row)
        mode = limits["mode"]
        quota = limits["quota"]
        quota_met = limits["quota_met"]
        count = c["{0}_{1}".format(*test)]
        waiting_quota = limits["waiting_quota"]
        waiting_quota_met = limits["waiting_quota_met"]
        waiting_smallquota = limits["waiting_smallquota"]
        waiting_count = c["waiting_{0}_{1}".format(*test)]

        overall_mode = _mode_precedence(overall_mode, mode)

        if quota is not None:
            spare = quota - count
            if spare <= 0 and not quota_met:
                logger.warning("quota_met should be set: %r", test)
                quota_met = True

            overall_quota_met = overall_quota_met or quota_met
        else:
            spare = None

        if waiting_quota is not None:
            waiting_spare = waiting_quota - waiting_count
            if waiting_spare <= 0 and not waiting_quota_met:
                logger.warning("waiting_quota_met should be set: %r", test)
                waiting_quota_met = True

            overall_waiting_quota_met = \
                    overall_waiting_quota_met or waiting_quota_met
        else:
            waiting_spare = None

        overall_spare = none_min(overall_spare, spare)
        overall_waiting_spare = none_min(overall_waiting_spare, waiting_spare)

        waiting_small = \
                _waiting_smallquota_test(waiting_small, waiting_smallquota,
                                         waiting_count)

        qpp = limits["quota_per_person"]
        if test[1] == 'any':
            overall_qpp_any = none_min(overall_qpp_any, qpp)
        else:
            overall_qpp_type = none_min(overall_qpp_type, qpp)

    return {"mode": overall_mode,
            "spare": overall_spare,
            "quota_met": overall_quota_met,
            "waiting_spare": overall_waiting_spare,
            "waiting_quota_met": overall_waiting_quota_met,
            "waiting_small": waiting_small,
            "qpp_any": overall_qpp_any,
            "qpp_type": overall_qpp_type}

def _test_keys(user_group, ticket_type):
    return ((user_group, ticket_type), (user_group, "any"),
            ("all", ticket_type), ("all", "any"))

def _mode_precedence(a, b):
    """
    return the 'largest' of `a` and `b`

    order: closed > not-yet-open > available
    """

    modes = ('closed', 'not-yet-open', 'available')
    assert a in modes and b in modes

    for o in modes:
        if a == o or b == o:
            return o
    else:
        raise AssertionError

def _waiting_smallquota_test(old_value, quota, waiting_count):
    if old_value is False:
        # another rule's smallquota was not met,
        # which takes precedence (think Order allow, deny)
        return False

    if quota is None:
        # no smallquota for this row
        # None -> None; True -> True
        return old_value

    if waiting_count < quota:
        # (None, True) -> True
        return True
    else:
        # (None, True) -> False
        return False

def quotas_per_person_sentence(user_group=None, pg=utils.postgres):
    """
    Get the quotas-per-person sentence for `user_group` (or the current user)
    """

    if user_group is None:
        user_group = _user_group_from_user(flask.session["user"])

    s = settings(pg=pg)

    for g in (user_group, 'all'):
        p = s.get((g, 'any'), {}).get('quota_per_person_sentence')
        if p is not None:
            return p
    else:
        raise AssertionError("qpp_sentence not set for {0}".format(user_group))

def mode_sentence(pg=utils.postgres):
    """Get the "mode sentence" (describes availability)"""
    return settings(pg=pg).get(('all', 'any'), {}).get("mode_sentence")

def none_min(a, b):
    """Return min(a, b), treating ``None`` as infinity"""
    if a is None:
        return b
    if b is None:
        return a
    else:
        return min(a, b)

def counts(drop_cache=False, pg=utils.postgres):
    """
    Counts various types in the tickets table

    Will used a cached result if `drop_cache` is ``False`` (and there is one
    available)

    Returns a dict, with keys
    ``{,waiting_}{all,members,alumni}_{any,standard,vip}`` and values being the
    respective counts
    """

    if not drop_cache and flask.current_app and \
            hasattr(flask.g, '_snowball_tickets_counts'):
        return flask.g._snowball_tickets_counts

    with pg.cursor(True) as cur:
        cur.execute(queries.unexpired_counts)
        c = cur.fetchone()

    if flask.current_app:
        flask.g._snowball_tickets_counts = c

    return c

def prices(user_group=None, pg=utils.postgres):
    """
    Gets ticket prices for `user_group` (or the current user)

    Returns a dict, ``{'standard': N, 'vip': N}``.
    """

    if user_group is None:
        user_group = _user_group_from_user(flask.session["user"])

    s = settings(pg=pg)
    r = {}

    for type in ('standard', 'vip'):
        for key in ((user_group, type), ('all', type),
                    (user_group, 'any'), ('all', 'any')):
            p = s.get(key, {}).get('price')
            if p is not None:
                r[type] = p
                break
        else:
            raise AssertionError("unset price for {0}"
                                    .format((user_group, type)))

    return r

def _user_group_from_user(user):
    """Return the user group for the user row `user`"""
    pt = user["person_type"]
    assert pt != 'non-cam'
    if pt == 'alumnus':
        return 'alumni'
    else:
        return 'members'

def settings(pg=utils.postgres):
    """Retrieve (with caching) the rows of the tickets_settings table"""

    if flask.current_app and hasattr(flask.g, '_snowball_tickets_settings'):
        return flask.g._snowball_tickets_settings

    key = ("who", "what")

    s = {}
    with pg.cursor(True) as cur:
        cur.execute("SELECT * FROM tickets_settings")
        for row in cur:
            row_key = tuple([row[k] for k in key])
            s[row_key] = row

    if flask.current_app:
        flask.g._snowball_tickets_settings = s

    return s

def tickets(user_id=None, vip=None, waiting_list=None, quota_exempt=None,
            finalised=None, paid=None, entered_ball=None, expired=None,
            pg=utils.postgres):
    """
    Return tickets for a user `user_id`, with filtering.
    
    For each of `finalised`, `paid` and `entered_ball` - if the argument is
    ``True`` then that timestamp must be non-null; ``False`` it is required
    to be null; ``None`` - no condition

    For `expires`, ``False`` demands the expires column be null, or in the
    future; ``True`` wants a non-null timestamp in the past.

    If `user_id` is ``None``, the current session's user is used.
    """

    if user_id is None:
        user_id = flask.session["user_id"]

    cond1 = _nully_conditions(finalised=finalised, paid=paid,
                              entered_ball=entered_ball)

    cond2 = _booly_conditions(vip=vip, waiting_list=waiting_list,
                              quota_exempt=quota_exempt)

    if expired is True:
        expires_cond = "(expires IS NOT NULL AND expires <= utcnow())"
    elif expired is False:
        expires_cond = "(expires IS NULL OR expires > utcnow())"
    else:
        expires_cond = "TRUE"

    cond = " AND ".join(["user_id = %s", expires_cond, cond1, cond2])
    query = "SELECT * FROM tickets WHERE " + cond

    with pg.cursor(True) as cur:
        cur.execute(query, (user_id, ))
        return cur.fetchall()

def _nully_conditions(**kwargs):
    """
    Generate IS [ NOT ] NULL conditions for the keys in `kwargs`

    Several columns in the tickets table are timestamps,
    where their being non-null indicates that something has happened;
    for example, `tickets.finalised` being non-null means that a ticket
    is finalised.

    For each key, where `value` is ``kwargs[key]``:

    *If `value` is ``None``, no condition is generated - i.e., "don't care" or
     "all"
    *If `value` is ``True``, produces the condition "{name} IS NOT NULL"
    *If `value` is ``False``, produces the condition "{name} IS NULL"

    The conditions are joined with ``AND`` and wrapped in parentheses
    """

    conditions = []

    for key, value in kwargs.items():
        if value is True:
            conditions.append(key + " IS NOT NULL")
        elif value is False:
            conditions.append(key + " IS NULL")

    if not conditions:
        return "TRUE"
    else:
        return "(" + ' AND '.join(conditions) + ")"

def _booly_conditions(**kwargs):
    """
    Generate conditions for the keys in `kwargs`

    For each key, where `value` is ``kwargs[key]``:

    *If `value` is ``None``, no condition is generated - i.e., "don't care" or
     "all"
    *If `value` is ``True``, produces the condition "{name}"
    *If `value` is ``False``, produces the condition "NOT {name}"

    The conditions are joined with ``AND`` and wrapped in parentheses
    """

    conditions = []

    for key, value in kwargs.items():
        if value is True:
            conditions.append(key)
        elif value is False:
            conditions.append("NOT " + key)

    if not conditions:
        return "TRUE"
    else:
        return "(" + ' AND '.join(conditions) + ")"


class BuyFailed(Exception):
    """A call to :func:`buy` failed"""

class InsufficientSpare(BuyFailed):
    """Insufficient spare tickets"""

class QPPAnyMet(BuyFailed):
    """Quota per person limit (any ticket type) met"""

class QPPTypeMet(BuyFailed):
    """Quota per person limit (specific ticket type) met"""

class FormRace(BuyFailed):
    """Between displaying options and submitting things changed"""

class IncorrectMode(FormRace):
    """Tickets are not ``available``"""

class QuotaMet(FormRace):
    """The quota has been met"""

class QuotaNotMet(FormRace):
    """The quota has not been met (and so you may not join the waiting list)"""

class WaitingQuotaMet(QuotaMet):
    """The waiting quota has been met"""

def buy(ticket_type, waiting_list, number, 
        user=None, quota_exempt=False, pg=utils.postgres):
    """Buy `user` `number` `ticket_type` tickets / add to waiting list."""

    if user is None:
        user = flask.session["user"]

    user_id = user["user_id"]
    user_group = _user_group_from_user(user)

    if not waiting_list:
        verb = ('buying', '')
    else:
        verb = ('adding', ' to the waiting list')
    log_prefix = "{0} {1} {2} tickets for user {3} ({4}){5}" \
            .format(verb[0], number, ticket_type, user_id, user_group, verb[1])

    # automatically released, recursive
    buy_lock(pg=pg)
    user_pg_lock(user["user_id"], pg=pg)

    vip = ticket_type == 'vip'

    # force a re-count having acquired the lock
    ticket_counts = counts(drop_cache=True, pg=pg)

    if not quota_exempt:
        avail = available(ticket_type, user_group=user_group, pg=pg)

        qpp_any_count = 0
        qpp_type_count = 0

        for ticket in tickets(user_id=user_id, expired=False,
                              quota_exempt=False, pg=pg):
            qpp_any_count += 1
            if ticket["vip"] == vip:
                qpp_type_count += 1

        qpp_any = avail["qpp_any"]
        qpp_type = avail["qpp_type"]

        if qpp_any is not None:
            if qpp_any < qpp_any_count + number:
                raise QPPAnyMet
        if qpp_type is not None:
            if qpp_type < qpp_type_count + number:
                raise QPPTypeMet

        if avail["mode"] != "available":
            logger.info("%s: not available (form race)", log_prefix)
            raise IncorrectMode

        if waiting_list and not avail["quota_met"]:
            logger.info("%s: wanted waiting list but quota not met (form race)",
                        log_prefix)
            raise QuotaNotMet

        if not waiting_list:
            quota_met = avail["quota_met"]
            spare = avail["spare"]
        else:
            quota_met = avail["waiting_quota_met"]
            spare = avail["waiting_spare"]

        if quota_met:
            logger.info("%s: quota met (form race)", log_prefix)
            if waiting_list:
                raise WaitingQuotaMet
            else:
                raise QuotaMet

        if spare is not None and spare < number:
            logger.info("%s: insufficient spare (%s < %s)", log_prefix,
                        spare, number)
            set_quota_met(user_group, ticket_type, waiting_list, number, pg=pg)
            raise InsufficientSpare

        elif spare == number:
            logger.info("%s: exactly met quota", log_prefix)
            set_quota_met(user_group, ticket_type, waiting_list, number, pg=pg)

    # else... OK. Make some tickets
    query = "INSERT INTO tickets (user_id, vip, waiting_list, price, "\
            " created, expires, expires_reason, quota_exempt) "
    values_row = "(%(user_id)s, %(vip)s, %(waiting_list)s, %(price)s, " \
                 "utcnow(), utcnow() + '10 minutes'::interval, " \
                 "'not-finalised', %(quota_exempt)s)"
    values = ', '.join([values_row] * number)
    query += "VALUES " + values + " RETURNING ticket_id"

    price = prices(user_group=user_group, pg=pg)[ticket_type]
    args = {"user_id": user_id, "vip": vip, "waiting_list": waiting_list,
            "price": price, "quota_exempt": quota_exempt}

    # if :func:`counts` is cached on flask.g, this will update it
    if waiting_list:
        p = "waiting_{0}_{1}"
    else:
        p = "{0}_{1}"

    for test in _test_keys(user_group, ticket_type):
        ticket_counts[p.format(*test)] += number

    with pg.cursor() as cur:
        cur.execute(query, args)
        ids = [r[0] for r in cur]

    logger.info("%s: inserted tickets %r", log_prefix, ids)
    return ids

def buy_lock(pg=utils.postgres):
    """Take out the transaction level postgres advisory lock for buying"""
    logger.debug("Acquiring buy lock")
    with pg.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s, %s)", buy_pg_lock_num)
    logger.debug("buy lock acquired")

def user_pg_lock(user_id, pg=utils.postgres):
    """
    Take out the transaction level postgres advisory lock for `user_id`
    
    This lock is acquired by :func:`buy`, :func:`finalise` and 
    :func:`receipt.send_update`.
    """
    logger.debug("Acquiring user %s lock", user_id)
    with pg.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s, %s)",
                    (user_pg_lock_num, user_id))
    logger.debug("user %s lock acquired", user_id)

def set_quota_met(user_group, ticket_type, waiting_list, number,
                  pg=utils.postgres):
    """
    Take action when a quota has been met.

    Suppose:
    
    * person A buys the last 4 tickets
    * person B then has to go on the waiting list
    * ten minutes later, A has not finalised their tickets and so they expire
    * person C coould now come and buy those 4 tickets, jumping B in the queue
    
    Hence: as soon as we `meet` the quota, change the mode.

    Note: this is not as soon as we go `over` the quota - hitting it exactly
    counts, since as soon as the quota is met the text will show
    'waiting list' on the buy buttons.
    """

    s = settings(pg=pg)
    c = counts(pg=pg)

    rows_quota_met = []
    rows_waiting_quota_met = []

    for test in _test_keys(user_group, ticket_type):
        limits = s.get(test, _null_settings_row)
        assert limits["mode"] == 'available'
        just_set_quota_met = False

        if not waiting_list:
            quota = limits["quota"]
            count = c["{0}_{1}".format(*test)]

            if quota is not None and not limits["quota_met"] and \
                    count + number >= quota:

                logger.warning("quota met: %r", test)
                rows_quota_met.append(test)

                # if `s` came from or was saved to the cache on flask.g,
                # this will update it.
                s.get(test, {})["quota_met"] = True

                # now check if the waiting quota has been met; it could happen
                # instantly
                just_set_quota_met = True

        if waiting_list or just_set_quota_met:
            quota = limits["waiting_quota"]
            count = c["waiting_{0}_{1}".format(*test)]
            if just_set_quota_met:
                number2 = 0
            else:
                number2 = number

            if quota is not None and not limits["waiting_quota_met"] and \
                    count + number2 >= quota:

                logger.warning("waiting quota met: %r", test)
                rows_waiting_quota_met.append(test)
                s.get(test, {})["waiting_quota_met"] = True

    if rows_quota_met:
        logger.info("set_quota_met: setting quota_met on rows %r", rows_quota_met)

        with pg.cursor() as cur:
            cur.execute("UPDATE tickets_settings SET quota_met = TRUE "
                        "WHERE (who, what) IN %s", (tuple(rows_quota_met), ))

    if rows_waiting_quota_met:
        logger.info("set_quota_met: setting waiting_quota_met on rows %r",
                    rows_waiting_quota_met)

        with pg.cursor() as cur:
            cur.execute("UPDATE tickets_settings SET waiting_quota_met = TRUE "
                        "WHERE (who, what) IN %s",
                        (tuple(rows_waiting_quota_met), ))

class FinaliseRace(Exception):
    """A race condition occured in :func:`finalise`"""

class AlreadyFinalised(FinaliseRace):
    """
    The ticket was already finalised
    
    .. attribute:: new_ticket

        The ticket, as it now exists in the database finalised.

    """
    def __init__(self, new_ticket):
        self.new_ticket = new_ticket

class NonExistantTicket(FinaliseRace):
    """The ticket does not exist"""

def finalise(ticket, update, pg=utils.postgres):
    """
    Finalise a ticket

    Essentially does this::
        
        ticket["finalised"] = datetime.utcnow()
        ticket.update(update)

    But also updates the corresponding database row, and will avoid a race.

    Does not check if the ticket is expired. Loading the tickets at the start
    of :func:`snowball_ticketing.tickets.views.details` should not race against
    the ticket expiring since ``utcnow()`` remains constant in a transaction.
 
    If the ticket is deleted between loading and updating,
    :class:`NonExistantTicket` will be raised and `ticket` won't be modified.

    If the ticket was already finalised, :class:`AlreadyFinalised` is raised.
    """

    assert ticket["finalised"] is None
    assert set(update) <= {"person_type", "surname", "othernames",
                           "college_id", "matriculation_year"}

    logger.debug("finalising ticket %s", ticket["ticket_id"])

    # protects against races with receipt
    user_pg_lock(ticket["user_id"], pg=pg)

    update = update.copy()
    # special case finalise to use utcnow()
    update["expires"] = None
    update["expires_reason"] = None

    sets = ', '.join("{0} = %({0})s".format(key) for key in update)

    query1 = "UPDATE tickets " \
             "SET finalised = utcnow(), " + sets + " " \
             "WHERE ticket_id = %(ticket_id)s AND finalised IS NULL " \
             "RETURNING *"
    query2 = "SELECT * FROM tickets WHERE ticket_id = %s"

    args = update
    args["ticket_id"] = ticket["ticket_id"]

    with pg.cursor(True) as cur:
        cur.execute(query1, args)
        assert cur.rowcount in (0, 1)

        if cur.rowcount == 1:
            # success
            ticket.update(cur.fetchone())
        else:
            # some race
            cur.execute(query2, (ticket["ticket_id"], ))
            assert cur.rowcount in (0, 1)
            if cur.rowcount == 1:
                raise AlreadyFinalised(cur.fetchone())
            else:
                raise NonExistantTicket

_reference_first_cleaner = re.compile("[^a-zA-Z0-9]")

def reference(user=None):
    """Get the payment reference `user` should use"""

    if user is None:
        user = flask.session["user"]

    if user["crsid"]:
        first = user["crsid"]
    else:
        first = _reference_first_cleaner.sub("", user["email"])[:9]

    # we're aiming for < 18 characters. The id isn't going to realistically
    # be longer than 4 characters, so this will work just fine.
    second = unicode(user["user_id"]).rjust(4, "0")

    return "{0}/{1}".format(first, second)

def outstanding_balance(user_id=None, ids_too=False, pg=utils.postgres):
    """
    Get the total unpaid for `user_id` (or the current user)
    
    If `ids_too` is ``True``, returns ``total unpaid, ticket_ids``
    """

    ts = tickets(user_id=user_id, finalised=True, paid=False,
                 waiting_list=False, pg=pg)

    bal = sum(t["price"] for t in ts)

    if ids_too:
        ids = [t["ticket_id"] for t in ts]
        return bal, ids
    else:
        return bal

def mark_paid(ticket_ids, add_note="", pg=utils.postgres):
    """Mark each of `ticket_ids` paid, optionally adding to `notes`"""

    query = "UPDATE tickets " \
            "SET paid = utcnow(), notes = notes || %s " \
            "WHERE ticket_id IN %s AND paid IS NULL"

    with pg.cursor() as cur:
        cur.execute(query, (add_note, tuple(ticket_ids)))
        assert cur.rowcount == len(ticket_ids)

def purge_unpaid(user_id, ticket_id, pg=utils.postgres):
    """
    Mark `ticket_id` unpaid and unfinalised

    `user_id` must match the `user_id` on the ticket (safety check).
    """

    query = "UPDATE tickets " \
            "SET finalised = NULL, expires = utcnow(), " \
            "    expires_reason = 'not-paid' " \
            "WHERE finalised IS NOT NULL AND paid IS NULL AND " \
            "      NOT waiting_list AND " \
            "      user_id = %s AND ticket_id = %s"

    logger.info("Purging ticket %s (not-paid)", ticket_id,
                extra={"user_id": user_id})

    with pg.cursor() as cur:
        cur.execute(query, (user_id, ticket_id))
        assert cur.rowcount == 1

def waiting_release(user_id, ticket_ids, ask_pay_within=7, pg=utils.postgres):
    """Release tickets to `user_id`, and send them an email"""

    query = "UPDATE tickets SET waiting_list = FALSE, notes = notes || %s " \
            "WHERE finalised IS NOT NULL AND waiting_list AND " \
            "      ticket_id IN %s AND user_id = %s"

    notes = "Released from waiting list on {0}\n".format(datetime.utcnow())
    logger.info("Releasing tickets %s from waiting list", list(ticket_ids),
                extra={"user_id": user_id})

    with pg.cursor() as cur:
        cur.execute(query, (notes, tuple(ticket_ids), user_id))
        assert cur.rowcount == len(ticket_ids)

    # :-( :-( circular import.
    from . import receipt
    receipt.send_update(user_id, pg=pg, ask_pay_within=ask_pay_within,
                        waiting_release=True)
