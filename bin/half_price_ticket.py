from __future__ import unicode_literals, print_function

import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import psycopg2
import logging

from snowball_ticketing import utils, users, tickets, lookup, logging_setup


logger = utils.getLogger(__name__)


def main(crsid, postgres_settings):
    logger.info("Creating half price ticket for %s", crsid)

    logging_setup.add_postgresql_handler(postgres_settings)
    logging_setup.add_syslog_handler()
    logging_setup.add_smtp_handler()

    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            **postgres_settings)

    user = users.get_raven_user(crsid, pg=conn)
    if user is None:
        conn.commit()
        lookup_data = lookup.get_crsid(crsid)
        user = users.new_raven_user(crsid, ["current"], lookup_data, pg=conn)

    if tickets.tickets(user_id=user["user_id"], expired=False, pg=conn):
        raise ValueError("User {0} already has some tickets"
                            .format(user["user_id"]))

    ticket_id, = tickets.buy("standard", True, 1, user=user, pg=conn)

    with conn.cursor() as cur:
        cur.execute("UPDATE tickets "
                    "SET waiting_list = FALSE, quota_exempt = TRUE, "
                    "    expires = NULL, expires_reason = NULL, "
                    "    price = 3450, notes = E'Ents half price ticket\n' "
                    "WHERE ticket_id = %s",
                    (ticket_id, ))

    conn.commit()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    if len(sys.argv) != 3 or sys.argv[2] not in ("live", "test"):
        print("Usage:", sys.argv[0], "crsid", "live|test")
    else:
        crsid = sys.argv[1]
        dbname = {"live": "ticketing", "test": "ticketing-test"}[sys.argv[2]]
        main(crsid, {"dbname": dbname})
