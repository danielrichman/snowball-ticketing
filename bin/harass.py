from __future__ import unicode_literals, print_function

import sys
import os
from datetime import datetime

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import psycopg2
import logging
import csv

from snowball_ticketing import utils, logging_setup
from snowball_ticketing.tickets.receipt import send_update


logger = utils.getLogger("snowball_ticketing.bin.harass")


def harass(postgres_settings, filename):
    logging_setup.add_syslog_handler()
    logging_setup.add_postgresql_handler(postgres_settings)
    logging_setup.add_smtp_handler()

    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            **postgres_settings)

    harassed = set()

    with open(filename) as f:
        for user_id, deadline in csv.reader(f):
            user_id = int(user_id)
            if user_id in harassed:
                logger.warning("Not double-harassing %s", user_id)
                continue

            harassed.add(user_id)

            deadline = datetime.strptime(deadline, "%Y-%m-%d").date()

            send_update(user_id, harass=True, deadline=deadline, pg=conn)
            conn.commit()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) != 2:
        print("Usage:", sys.argv[0], "filename.csv")
    else:
        _, filename = sys.argv
        harass({"dbname": "ticketing"}, filename)
