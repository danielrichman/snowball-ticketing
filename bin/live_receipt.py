import sys
import os
import logging

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

from snowball_ticketing.tickets.receipt import receipts_main
from snowball_ticketing import logging_setup

postgres = {"database": "ticketing"}

logging_setup.add_postgresql_handler(postgres)
logging_setup.add_syslog_handler()
logging_setup.add_smtp_handler()

receipts_main(postgres)
