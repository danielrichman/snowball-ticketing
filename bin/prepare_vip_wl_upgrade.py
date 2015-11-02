from __future__ import unicode_literals, print_function

import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import psycopg2
import logging
import csv
from datetime import datetime

from snowball_ticketing import utils, tickets, logging_setup


logger = utils.getLogger("snowball_ticketing.bin.prepare_vip_wl_upgrade")


def prepare(postgres_settings, pairs):
    # This is a hack, to cover up a design flaw.

    logging_setup.add_syslog_handler()
    logging_setup.add_postgresql_handler(postgres_settings)
    logging_setup.add_smtp_handler()

    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            **postgres_settings)

    for user_id, ticket_id in pairs:
        with conn.cursor(True) as cur:
            cur.execute("SELECT * FROM tickets "
                        "WHERE ticket_id = %s AND user_id = %s",
                        (ticket_id, user_id))
            assert cur.rowcount == 1
            ticket = cur.fetchone()

            cur.execute("SELECT * FROM tickets "
                        "WHERE user_id = %s AND surname = %s "
                        "AND othernames = %s AND finalised IS NOT NULL",
                        (user_id, ticket["surname"], ticket["othernames"]))
            if cur.rowcount != 2:
                print("Couldn't find standard ticket for", user_id, ticket_id)
                continue

            standard_ticket, b = cur.fetchall()
            if standard_ticket["ticket_id"] == ticket_id:
                standard_ticket = b

            if standard_ticket["waiting_list"] or standard_ticket["vip"] \
                    or not standard_ticket["paid"]:
                print("Bad standard ticket for", user_id, ticket_id)
                continue

            logger.info("Preparing waiting ticket %s to VIP upgrade %s",
                        ticket_id, standard_ticket["ticket_id"],
                        extra={"user_id": user_id})

            notes = "Prepared to replace {0} " \
                    "(VIP upgrade waiting list release) on {1}\n" \
                        .format(standard_ticket["ticket_id"],
                                datetime.utcnow())
            cur.execute("UPDATE tickets "
                        "SET price = 1000, notes = notes || %s "
                        "WHERE ticket_id = %s AND user_id = %s",
                        (notes, ticket_id, user_id))

            notes = "Replaced by VIP ticket {0} from waiting list on {1}\n" \
                        .format(ticket_id, datetime.utcnow())
            cur.execute("UPDATE tickets "
                        "SET expires=utcnow(), "
                        "    expires_reason='admin-intervention', "
                        "    finalised=NULL, paid=NULL, "
                        "    notes = notes || %s "
                        "WHERE ticket_id = %s AND user_id = %s",
                        (notes, standard_ticket["ticket_id"], user_id))

            conn.commit()

def load_ids(filename):
    """Yields (user_id, ticket_id) pairs"""
    with open(filename) as f:
        for row in csv.reader(f):
            yield tuple(int(x) for x in row)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) != 2:
        print("Usage:", sys.argv[0], "filename.csv")
    else:
        _, filename = sys.argv
        prepare({"dbname": "ticketing"}, load_ids(filename))
