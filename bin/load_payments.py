from __future__ import unicode_literals, print_function

import sys
import os
import logging

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

from snowball_ticketing.tickets.payments import main
from snowball_ticketing import logging_setup

logging.basicConfig(level=logging.DEBUG)

logging_setup.add_smtp_handler()

if len(sys.argv) != 4 or \
        sys.argv[1] not in ('live', 'test') or \
        sys.argv[3] not in ('dry-run', 'confirm'):
    print("Usage:", sys.argv[0], "live|test", "filename.csv",
            "dry-run|confirm")

else:
    postgres_settings = {"live": {"dbname": "ticketing"},
                         "test": {"dbname": "ticketing-test"}}[sys.argv[1]]
    dry_run = sys.argv[3] == "dry-run"
    if not dry_run:
        logging_setup.add_syslog_handler()
        logging_setup.add_postgresql_handler(postgres_settings)
    main(sys.argv[2], dry_run, postgres_settings)
