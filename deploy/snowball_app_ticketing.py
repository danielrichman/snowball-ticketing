import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

from snowball_ticketing import utils, logging_setup
from snowball_ticketing.apps.ticketing import app

postgres = {"database": "ticketing"}

app.config["POSTGRES"] = postgres

logging_setup.remove_gunicorn_syslog_handler()
logging_setup.add_postgresql_handler(postgres)
logging_setup.add_syslog_handler()
logging_setup.add_smtp_handler()

application = app
