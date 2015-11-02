from __future__ import unicode_literals, print_function

import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import psycopg2
import logging

from snowball_ticketing import utils, users, tickets, lookup, logging_setup


logger = utils.getLogger("manual_add_unfinalised_ticket")


# Stolen from user_info.py
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

def main(postgres_settings):
    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            **postgres_settings)

    logging_setup.add_postgresql_handler(postgres_settings)
    logging_setup.add_syslog_handler()
#    logging_setup.add_smtp_handler()

    crsid = raw_input("CRSid of the Cambridge student responsible for the ticket: ").strip()

    if not crsid:
        sys.exit(1)

    user = users.get_raven_user(crsid, pg=conn)
    if user is None:
        conn.commit()
        lookup_data = lookup.get_crsid(crsid)
        user = users.new_raven_user(crsid, ["current"], lookup_data, pg=conn)
    else:
        print("They already have an account:")

    print("Surname:", user["surname"])
    print("Othernames:", user["othernames"])
    print("College:", utils.college_name(user["college_id"], pg=conn))
    print()

    ts = tickets.tickets(user_id=user["user_id"], pg=conn)

    if ts:
        ts.sort(key=lambda t: (t["surname"], t["othernames"],
                               t["waiting_list"], not t["vip"]))
        print("They currently have these tickets:")
        for ticket in ts:
            print("    {0}:".format(ticket["ticket_id"]).ljust(4 + 5),
                  ticket["othernames"], ticket["surname"],
                  "(" + types(ticket) + ")")
        print()

    # Don't idle in transaction.
    conn.commit()

    print("To cancel, press Ctrl-C.")
    while True:
        try:
            num = int(raw_input("Number of tickets: ").strip())
        except ValueError:
            continue
        else:
            if 1 <= num <= 200:
                break

    while True:
        ticket_type = raw_input("Standard or VIP: ").strip().lower()
        if ticket_type in {"vip", "standard"}:
            break

    while True:
        free = raw_input("Should the tickets be free? [yes|no] ").strip().lower()
        if free in {"y", "yes"}:
            free = True
            break
        elif free in {"n", "no"}:
            free = False
            break

    notes = raw_input("Comment (stored against the ticket): ").strip()
    if notes:
        notes += "\n"
    notes = "Added using manual_add_unfinalised_ticket.py\n" + notes

    logger.info("Creating %s %s%s ticket(s)", num, ticket_type, " free" if free else "")

    ids = tickets.buy(ticket_type, False, num, user=user, quota_exempt=True, pg=conn)

    with conn.cursor() as cur:
        cur.execute("UPDATE tickets "
                    "SET expires = NULL, expires_reason = NULL, "
                    "    notes = %s "
                    "WHERE ticket_id in %s", (notes, tuple(ids)))

        if free:
            cur.execute("UPDATE tickets SET price = 0 WHERE ticket_id in %s",
                        (tuple(ids), ))

    conn.commit()

    print()
    print("Done. Next step: inform the user that they should log into the website.")
    print("They will see the following message:")
    print("  You reserved N tickets recently, but are yet to fill out the details on them.")
    print("  [Resume order]")
    print("(there is no time limit)")
    print("and they can then put the names on their tickets.")
    print()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    if len(sys.argv) != 2 or sys.argv[1] not in ("live", "test"):
        print("Usage:", sys.argv[0], "live|test")
    else:
        dbname = {"live": "ticketing", "test": "ticketing-test"}[sys.argv[1]]
        main({"dbname": dbname})
