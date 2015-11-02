from __future__ import unicode_literals, print_function

import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import logging
import psycopg2

from snowball_ticketing import tickets, utils, users, logging_setup


logger = utils.getLogger("snowball_ticketing.bin.guest_mass_mail")


def send_mail(template, user_id, pg):
    user = users.get_user(user_id, pg=pg)
    name = user["othernames"] + " " + user["surname"]

    logger.info("Sending mass mail (%s) to user %s",
                template, user["user_id"],
                extra={"user_id": user_id})

    # drop the locks
    pg.commit()

    utils.send_email(template, recipient=(name, user["email"]),
                     sender=("Snowball Ticketing",
                             "ticketing@selwynsnowball.co.uk"))

def main(postgres_settings, template, filename):
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

            send_mail(template, user_id, pg=conn)
            conn.commit()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) != 3:
        print("Usage:", sys.argv[0], "template", "user_ids.csv")
    else:
        _, template, filename = sys.argv
        main({"dbname": "ticketing"}, template, filename)
