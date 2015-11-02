from __future__ import unicode_literals, print_function

import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import psycopg2
import logging
from datetime import datetime

from snowball_ticketing import utils, tickets


def keys(what, which, pg):
    def rowstart(key): return ("    " + key + ":").ljust(39)

    for key in which:
        if key == "college_name":
            value = utils.college_name(what["college_id"], pg=pg)
        else:
            value = what[key]
        if value is None:
            value = ""
        print(rowstart(key), value)

def types(ticket):
    a = []
    if ticket["vip"]: a.append("VIP")
    if ticket["paid"]: a.append("paid")
    elif ticket["finalised"]: a.append("finalised")
    elif ticket["expires"] is not None and \
         ticket["expires"] < datetime.utcnow(): a.append("expired")
    for key in ('waiting_list', 'quota_exempt', 'printed',
                'ticket_collected', 'entered_ball',
                'forbid_desk_entry'):
        if ticket[key]: a.append(key.replace("_", "-"))
    return ' '.join(a)

def notes(title, string):
    print("    " + title + ":")
    for line in string.strip().splitlines():
        print("        " + line)

def search(key, value, expired, postgres_settings):
    assert key in ("crsid", "surname", "email", "user_id", "ticket_id")

    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            **postgres_settings)

    if key == "user_id":
        query = "SELECT * FROM users WHERE user_id = %s"
    elif key == "ticket_id":
        query = "SELECT users.* FROM tickets " \
                "JOIN users ON users.user_id = tickets.user_id " \
                "WHERE ticket_id = %s"
    else:
        query = "SELECT * FROM users WHERE lower({0}) = %s".format(key)
        value = value.lower()

    with conn.cursor(True) as cur:
        cur.execute(query, (value, ))
        if cur.rowcount == 0:
            raise ValueError("No user found")
        elif cur.rowcount != 1:
            print("Multiple users:")
            for user in cur:
                if user["person_type"] == "alumnus":
                    user["id"] = user["email"]
                else:
                    user["id"] = user["crsid"]
                user["user_id"] = "{0}:".format(user["user_id"]).ljust(5)
                info = "{user_id} {othernames} {surname} {id}".format(**user)
                print("    " + info)
        else:
            user = cur.fetchone()
            user_info(user, pg=conn)

def user_info(user, pg):
    print("User", user["user_id"])
    user["outstanding_balance"] = \
            tickets.outstanding_balance(user_id=user["user_id"], pg=pg)
    user["reference"] = tickets.reference(user)
    keys(user, ("othernames", "surname", "person_type", "college_name",
                "crsid", "email", "outstanding_balance", "reference"),
         pg=pg)
    if user["notes"]:
        notes("notes", user["notes"])
    print()

    ts = tickets.tickets(user_id=user["user_id"], expired=expired, pg=pg)

    ts.sort(key=lambda t: (t["surname"], t["othernames"],
                           t["waiting_list"], not t["vip"]))
    print("Tickets summary")
    for ticket in ts:
        print("    {0}:".format(ticket["ticket_id"]).ljust(4 + 5),
              ticket["othernames"], ticket["surname"],
              "(" + types(ticket) + ")")
    print()

    ts.sort(key=lambda t: t["ticket_id"])
    for ticket in ts:
        print("Ticket", ticket["ticket_id"], types(ticket),
              utils.pounds_pence(ticket["price"]))
        keys(ticket, ("created", "expires", "expires_reason", "finalised",
                      "paid", "othernames", "surname", "person_type",
                      "college_name"),
             pg=pg)
        if ticket["notes"]:
            notes("notes", ticket["notes"])
        if ticket["desk_notes"]:
            notes("desk_notes", ticket["desk_notes"])
        print()

    with pg.cursor() as cur:
        cur.execute("SELECT created, session_id, message "
                    "FROM log WHERE user_id = %s",
                    (user["user_id"], ))
        for created, session_id, message in cur:
            session_id = str(session_id).ljust(5)
            print(created, session_id, message)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) not in (3, 4) or \
            sys.argv[1] not in ("crsid", "surname", "email",
                                "user_id", "ticket_id") or \
            (len(sys.argv) == 4 and sys.argv[3] != "expired"):
        print("Usage:", sys.argv[0],
              "crsid|surname|email|user_id|ticket_id",
              "search-value", "[expired]")
    else:
        _, key, value = sys.argv[:3]
        if len(sys.argv) == 4:
            expired = None
        else:
            expired = False
        if key == "user_id":
            value = int(value)
        search(key, value, expired, {"dbname": "ticketing"})
