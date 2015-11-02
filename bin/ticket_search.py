from __future__ import unicode_literals, print_function

import sys
import os
import csv

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import psycopg2
import logging
from datetime import datetime

from snowball_ticketing import utils, tickets

def types(ticket):
    a = []
    if ticket["vip"]: a.append("VIP")
    if ticket["waiting_list"]: a.append("waiting-list")
    if ticket["paid"]: a.append("paid")
    elif ticket["finalised"]: a.append("finalised")
    elif ticket["expires"] is not None and \
         ticket["expires"] < datetime.utcnow(): a.append("expired")
    if ticket["quota_exempt"]: a.append("quota-exempt")
    return ' '.join(a)

def summarise(ticket):
    return ticket["othernames"] + " " + ticket["surname"] + " " + types(ticket)

def main():
    logging.basicConfig(level=logging.INFO)

    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            dbname="ticketing")

    writer = csv.writer(sys.stdout)

    query = "SELECT * FROM tickets " \
            "WHERE lower(surname) = %s AND " \
            "   (expires IS NULL OR expires > utcnow())"

    for surname in sys.stdin:
        surname = surname.strip().lower()
        with conn.cursor(True) as cur:
            cur.execute(query, (surname, ))
            writer.writerow([surname, ','.join(summarise(t) for t in cur)])

if __name__ == "__main__":
    main()
