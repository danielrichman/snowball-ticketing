import sys
import os
import logging

import gevent.wsgi
import werkzeug.serving
import werkzeug.debug

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

from snowball_ticketing.apps.admin import app

postgres = {"database": "ticketing-test"}

app.config["POSTGRES"] = postgres
# else it would keep postgresql connections open when the debugger starts
app.config["PRESERVE_CONTEXT_ON_EXCEPTION"] = False
app.config["SESSION_COOKIE_SECURE"] = False

logging.basicConfig(level=logging.DEBUG)

app.run(debug=True)
