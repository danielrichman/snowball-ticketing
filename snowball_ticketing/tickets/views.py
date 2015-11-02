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

"""tickets - (customer) ticket views"""

from __future__ import unicode_literals

from datetime import datetime
from calendar import timegm
import re

import flask
from flask import render_template, session, request, redirect, url_for, abort

from .. import utils, users, tickets


#: the :class:`flask.Blueprint` containing (customer) ticket views
bp = flask.Blueprint('tickets', __name__)


@bp.route("/tickets")
@utils.requires_session
def home():
    # A few of these queries could technically race against each other.
    # As far as I can tell, nothing bad can come of this.

    # get availablity, modes - used below in qpp and buttons
    avail = {}
    modes = {}

    for t in ('standard', 'vip'):
        avail[t] = tickets.available(t)
        modes[t] = avail[t]["mode"]

        # use pseudo-modes for simplicity
        if modes[t] == "available" and avail[t]["quota_met"]:
            if avail[t]["waiting_quota_met"]:
                modes[t] = "closed"
            elif avail[t]["waiting_small"]:
                modes[t] = "waiting-list-small"
            else:
                modes[t] = "waiting-list"

    # count up tickets, collect finalised tickets, calculate deadline
    user_counts = {"any": 0, "vip": 0, "standard": 0, "unfinalised": 0}
    deadline = None
    finalised_tickets = []

    for ticket in tickets.tickets(expired=False):
        user_counts["any"] += 1
        if not ticket["quota_exempt"]:
            if ticket["vip"]:
                user_counts["vip"] += 1
            else:
                user_counts["standard"] += 1

        if ticket["finalised"] is None:
            user_counts["unfinalised"] += 1
            deadline = tickets.none_min(deadline, ticket["expires"])
        else:
            finalised_tickets.append(ticket)

    # for the javascript
    if deadline is not None:
        deadline = timegm(deadline.utctimetuple())

    def s(t): return t["waiting_list"], not t["vip"], t["finalised"]
    finalised_tickets.sort(key=s)

    # calculate qpp status
    qpp_reached = {}
    spaces = []

    for t in ('standard', 'vip'):
        qpp_any = avail[t]["qpp_any"]
        qpp_type = avail[t]["qpp_type"]
        space = None

        if qpp_any is not None:
            space = tickets.none_min(space, qpp_any - user_counts["any"])
        if qpp_type is not None:
            space = tickets.none_min(space, qpp_type - user_counts[t])

        spaces.append(space)
        qpp_reached[t] = space is not None and space <= 0

    if None in spaces:
        qpp_max_space = None
    else:
        qpp_max_space = max(spaces)

    # final button setup
    enable_buttons = {}
    for t in ('standard', 'vip'):
        mode_ok = modes[t] not in ("not-yet-open", "closed")
        enable_buttons[t] = mode_ok and not qpp_reached[t]

    return render_template("tickets/home.html",
            prices=tickets.prices(),
            ticket_modes=modes,
            mode_sentence=tickets.mode_sentence(),
            qpp_sentence=tickets.quotas_per_person_sentence(),
            qpp_reached=qpp_reached,
            qpp_max_space=qpp_max_space,
            buy_more=bool(user_counts["any"]),
            enable_buttons=enable_buttons,
            success_notice=bool("success" in request.args),
            finalised_tickets=finalised_tickets,
            unfinalised_tickets=user_counts["unfinalised"],
            deadline=deadline,
            payment_reference=tickets.reference(),
            outstanding_balance=tickets.outstanding_balance())

@bp.route("/tickets/terms")
def terms():
    return render_template("tickets/terms.html")

@bp.route("/tickets/hide_instructions", methods=["POST"])
@utils.requires_session
@utils.requires_ajax
def hide_instructions():
    users.update_user(session["user_id"], hide_instructions=True)
    return "OK"

@bp.route("/tickets/buy", methods=["POST"])
@utils.requires_session
@utils.requires_csrf
def buy():
    try:
        number = request.form["number"]
        ticket_type = request.form["type"]
        if ticket_type not in ("standard", "vip"):
            raise ValueError
    except (KeyError, ValueError):
        abort(400)

    try:
        number = int(number)
        if number < 1:
            raise ValueError
    except ValueError:
        return render_template("tickets/buy_failed.html", reason='bad_number')

    waiting_list_key = "waiting_list_" + ticket_type
    waiting_list = request.form.get(waiting_list_key) == "yes"

    suggest_waiting_list = False
    success = False
    qpp_value = None
    reason = None

    try:
        tickets.buy(ticket_type, waiting_list, number)

    except (tickets.InsufficientSpare):
        reason = 'insufficient spare'
        suggest_waiting_list = 'maybe'

    except tickets.QPPAnyMet:
        reason = 'qpp any'
        qpp_value = tickets.available(ticket_type)["qpp_any"]

    except tickets.QPPTypeMet:
        reason = 'qpp type'
        qpp_value = tickets.available(ticket_type)["qpp_type"]

    except tickets.FormRace:
        reason = 'form race'
        suggest_waiting_list = 'maybe'

    else:
        success = True

    if suggest_waiting_list == 'maybe':
        if not waiting_list:
            avail = tickets.available(ticket_type)
            suggest_waiting_list = avail["quota_met"] and \
                    not avail["waiting_quota_met"] and \
                    avail["waiting_small"]
        else:
            suggest_waiting_list = False

    if success:
        return redirect(url_for('.details'))
    else:
        return render_template("tickets/buy_failed.html", reason=reason,
                               waiting_list=waiting_list, number=number,
                               ticket_type=ticket_type,
                               suggest_waiting_list=suggest_waiting_list,
                               qpp_value=qpp_value)

@bp.route("/tickets/details", methods=["GET", "POST"])
@utils.requires_session
@utils.requires_csrf
def details():
    deadline = None

    finalised_tickets = []
    unfinalised_tickets = []

    non_expired_ids = set()
    already_finalised_ids = set()

    for ticket in tickets.tickets(expired=False):
        # get changes from form
        if ticket["finalised"] is None:
            form = ticket.copy()
            _ticket_form(form)

            # ... and maybe finalise
            if form["ok"] and request.method == "POST":
                try:
                    tickets.finalise(ticket, form["update"])
                except AlreadyFinalised as e:
                    # this will set "submitted_finalised"
                    already_finalised_ids.add(ticket["ticket_id"])
                    ticket = e.new_ticket
                    assert ticket["finalised"] is not None
                except NonExistantTicket:
                    # thereby skipping "non_expired_ids.add" and setting
                    # a submitted_expired error
                    continue

        else:
            already_finalised_ids.add(ticket["ticket_id"])

        # for tracking submissions to expired tickets
        # note - this is below the 'continue' statement above.
        non_expired_ids.add(ticket["ticket_id"])

        # put ticket into the right list; check deadline if apt.
        if ticket["finalised"] is None:     # is /still/ None
            unfinalised_tickets.append(form)
            deadline = tickets.none_min(deadline, ticket["expires"])
        else:
            finalised_tickets.append(ticket)

    # check to see if they tried to save changes to expired tickets
    submitted = set(_submitted_tickets())
    submitted_expired = submitted - non_expired_ids
    submitted_finalised = submitted & already_finalised_ids

    # prepare deadline info
    if deadline is not None:
        deadline = timegm(deadline.utctimetuple())

    # sort tickets
    def compare(a, b):
        a1 = (a["waiting_list"], a["vip"])
        b1 = (b["waiting_list"], b["vip"])
        if a1 < b1:
            return -1
        elif a1 > b1:
            return 1

        # ok, now compare expires.
        smaller = tickets.none_min(a["expires"], b["expires"])
        if a["expires"] == b["expires"] == smaller:
            return 0
        elif a["expires"] == smaller:
            return -1
        else:
            return 1
    unfinalised_tickets.sort(cmp=compare)
    finalised_tickets.sort(cmp=compare)

    # enable/disable the "you agree to pay" notice
    waiting_lists = [t["waiting_list"]
                     for t in unfinalised_tickets + finalised_tickets]
    if all(waiting_lists):
        payment_notice = False
    elif any(waiting_lists):
        payment_notice = "mixed"
    else:
        payment_notice = "all"

    # if first purchase, assume the first ticket is for 'me'
    if request.method == "GET" and unfinalised_tickets and \
            not finalised_tickets:
        unfinalised_tickets[0]["person_type"] = \
                {"value": "me", "error": False, "empty": False}

    # all done? go back to home, but only if there arn't any errors to show
    if not (unfinalised_tickets or submitted_expired or submitted_finalised):
        return redirect(url_for(".home", success=True))

    # for JS
    unfinalised_ticket_ids = [t["ticket_id"] for t in unfinalised_tickets]

    return render_template("tickets/details.html",
                           submitted_expired=submitted_expired,
                           submitted_finalised=submitted_finalised,
                           deadline=deadline,
                           finalised_tickets=finalised_tickets,
                           unfinalised_tickets=unfinalised_tickets,
                           unfinalised_ticket_ids=unfinalised_ticket_ids,
                           payment_notice=payment_notice)

_submitted_tickets_re = re.compile(r"^(\d+)_form_person_type$")
def _submitted_tickets():
    for key in request.form:
        m = _submitted_tickets_re.match(key)
        if m:
            try:
                yield int(m.groups()[0])
            except ValueError:
                pass

def _ticket_form(ticket):
    def fk(x): return "{0}_{1}".format(ticket["ticket_id"], x)

    ticket["update"] = {}
    ok = True

    # This is the person-type of the form when it was _loaded_ and
    # therefore tells us which inputs were visible before submitting.
    # This will be the same as person_type if they have javascript,
    # since then things are automatically hidden/shown.
    form_person_type = request.form.get(fk("form_person_type"), None)

    # if the ticket wasn't submitted, don't complain about empty values
    # ticket_was_in_form is tested when deciding whether to complain
    # about person_type; otherwise form_person_type == 'None' means
    # "no person_type selected" (either by non-submission or non-selection)
    # and other fields therefore don't complain
    ticket_was_in_form = form_person_type is not None
    if form_person_type == '':
        form_person_type = None

    # person_type
    person_type = request.form.get(fk("person_type"), '')

    if person_type not in ('', 'me', 'undergraduate', 'postgraduate',
                           'staff', 'cam-other', 'alumnus', 'non-cam'):
        abort(400)

    if person_type == 'me':
        # 'me' handling
        for copy in ("person_type", "surname", "othernames",
                     "college_id", "matriculation_year"):
            ticket["update"][copy] = session["user"][copy]

        ticket["person_type"] = \
                {"value": 'me', "error": False, "empty": False}

    elif person_type == '':
        # empty person type handling
        person_type = None
        ok = False

        # only complain if the form was visible
        empty = ticket_was_in_form
        ticket["person_type"] = \
                {"value": None, "error": empty, "empty": empty}

    # surname, othername
    if person_type not in (None, 'me'):
        ticket["person_type"] = \
                {"value": person_type, "error": False, "empty": False}
        ticket["update"]["person_type"] = person_type

        for key in ("surname", "othernames"):
            value = request.form.get(fk(key), '').strip()
            empty = value == ""
            ticket["update"][key] = value
            ok = ok and not empty

            # don't complain if the inputs wern't visible before
            empty2 = empty and form_person_type not in ('me', None)
            ticket[key] = \
                    {"value": value, "empty": empty2, "error": empty2}

    else:
        ticket["surname"] = ticket["othernames"] = \
                {"value": '', "error": False, "empty": False}

    # college_id
    if person_type not in (None, 'me', 'non-cam'):
        value = request.form.get(fk("college_id"), '')
        empty = value == ""
        if not empty:
            try:
                value = int(value)
                if value not in utils.all_colleges():
                    raise ValueError
            except ValueError:
                abort(400)
        else:
            value = None

        ticket["update"]["college_id"] = value
        ok = ok and not empty

        # only complain if it was visible before
        empty2 = empty and form_person_type not in (None, 'me', 'non-cam')
        ticket["college_id"] = \
                {"value": value, "empty": empty2, "error": empty2}

    else:
        ticket["college_id"] = \
                {"value": None, "empty": False, "error": False}

    # matriculation_year
    if person_type == 'alumnus':
        value = request.form.get(fk("matriculation_year"), '').strip()
        empty = value == ""
        invalid = future = False
        if not empty:
            try:
                value = utils.parse_matriculation_year(value)
            except utils.MatriculationTimetravel:
                future = True
            except ValueError:
                invalid = True
        error = future or invalid or empty
        ticket["update"]["matriculation_year"] = value
        ok = ok and not error

        # only complain about empty errors if visible before
        empty2 = empty and form_person_type == 'alumnus'
        error2 = future or invalid or empty2
        ticket["matriculation_year"] = \
                {"value": value, "error": error2, "empty": empty2,
                 "invalid": invalid, "future": future}

    else:
        ticket["matriculation_year"] = \
                {"value": '', "empty": False, "error": False,
                 "invalid": False, "future": False}

    ticket["ok"] = ok
