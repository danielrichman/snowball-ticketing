from __future__ import unicode_literals, print_function

import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import psycopg2
import logging
import csv

from snowball_ticketing import utils, tickets, logging_setup


def release(postgres_settings, pairs):
    logging_setup.add_syslog_handler()
    logging_setup.add_postgresql_handler(postgres_settings)
    logging_setup.add_smtp_handler()

    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            **postgres_settings)

    for user_id, ticket_ids in pairs:
        tickets.waiting_release(user_id, ticket_ids,
                                ask_pay_within=1, pg=conn)
        conn.commit()

def load_ids(filename):
    """Returns a list of (user_id, set(ticket_ids)) pairs"""
    users = {}
    with open(filename) as f:
        for row in csv.reader(f):
            user_id, ticket_id = [int(x) for x in row]
            users.setdefault(user_id, set()).add(ticket_id)
    return users.items()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) != 2:
        print("Usage:", sys.argv[0], "filename.csv")
    else:
        _, filename = sys.argv
        release({"dbname": "ticketing"}, load_ids(filename))
