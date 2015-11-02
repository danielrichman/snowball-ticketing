from __future__ import unicode_literals, print_function

import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import logging
import psycopg2

from snowball_ticketing import tickets, utils, users, logging_setup


logger = utils.getLogger("snowball_ticketing.bin.collection_mass_mail")


def send_mail(user_id, pg):
    tickets.user_pg_lock(user_id, pg=pg)

    user = users.get_user(user_id, pg=pg)
    name = user["othernames"] + " " + user["surname"]
    alumnus = user["person_type"] == "alumnus"

    paid_tickets = tickets.tickets(user_id=user_id, paid=True, pg=pg)
    if not paid_tickets:
        logger.warning("Not mailing %s (no tickets)", user_id, extra={"user_id": user_id})
        return

    def k(t): return (t["othernames"], t["surname"])
    paid_tickets.sort(key=k)

    logger.info("Sending pickup mail to user %s; paid tickets %r",
                user["user_id"],
                [t["ticket_id"] for t in paid_tickets],
                extra={"user_id": user_id})

    # drop the locks
    pg.commit()

    utils.send_email("correction.txt", recipient=(name, user["email"]),
                     sender=("Snowball Ticketing",
                             "ticketing@selwynsnowball.co.uk"),
                     paid_tickets=paid_tickets,
                     alumnus=alumnus)

def main(postgres_settings, filename):
    logging_setup.add_syslog_handler()
    logging_setup.add_postgresql_handler(postgres_settings)
    logging_setup.add_smtp_handler()

    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            **postgres_settings)

    mailed = set()

    with open(filename) as f:
        for line in f:
            user_id = int(line.strip())
            if user_id in mailed:
                logger.warning("Not double-mailing %s", user_id)
                continue

            mailed.add(user_id)

            send_mail(user_id, pg=conn)
            conn.commit()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) != 2:
        print("Usage:", sys.argv[0], "filename.csv")
    else:
        _, filename = sys.argv
        main({"dbname": "ticketing"}, filename)
