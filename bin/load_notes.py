from __future__ import unicode_literals, print_function

import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import psycopg2
import logging
import csv

from snowball_ticketing import utils

def main(input_file, postgres_settings):
    conn = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                            **postgres_settings)

    with conn.cursor() as cur:
        for user_id, crsid, email, notes in csv.reader(input_file):
            notes = notes.decode("utf8")
            query = "UPDATE users SET notes = notes || %s WHERE TRUE"
            args = [notes.strip() + "\n"]

            assert user_id.strip() or crsid or email

            if user_id.strip():
                query += " AND user_id = %s"
                args.append(int(user_id))

            if crsid:
                query += " AND crsid = %s"
                args.append(crsid)

            if email:
                query += " AND email = %s"
                args.append(email)

            cur.execute(query, args)
            assert cur.rowcount <= 1
            if cur.rowcount != 1:
                print("Row", user_id, crsid, email, "modified", cur.rowcount, "rows")

    conn.commit()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main(sys.stdin, {"dbname": "ticketing"})
