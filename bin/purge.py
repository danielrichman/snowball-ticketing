from __future__ import unicode_literals, print_function

import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import psycopg2
import logging
import csv

from snowball_ticketing import utils, tickets, logging_setup


def purge(postgres_settings, pairs):
    logging_setup.add_syslog_handler()
    logging_setup.add_postgresql_handler(postgres_settings)
    logging_setup.add_smtp_handler()

    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            **postgres_settings)

    for user_id, ticket_id in pairs:
        tickets.purge_unpaid(user_id, ticket_id, pg=conn)
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
        purge({"dbname": "ticketing"}, load_ids(filename))
