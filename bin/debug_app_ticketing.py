import gevent.monkey

# werkzeug reloader thread uses time.time and thread.start_thread
gevent.monkey.patch_time()
gevent.monkey.patch_thread()

import sys
import os
import logging
import functools

import gevent.wsgi
import werkzeug.serving
import werkzeug.debug

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

from snowball_ticketing.apps.ticketing import app
from snowball_ticketing import logging_setup

postgres = {"database": "ticketing-test"}

app.config["POSTGRES"] = postgres
# else it would keep postgresql connections open when the debugger starts
app.config["PRESERVE_CONTEXT_ON_EXCEPTION"] = False
app.config["SESSION_COOKIE_SECURE"] = False
app.debug = True

logging.basicConfig(level=logging.DEBUG)
logging_setup.add_postgresql_handler(postgres)

app = werkzeug.debug.DebuggedApplication(app, True)
ws = gevent.wsgi.WSGIServer(('localhost', 5000), app)
werkzeug.serving.run_with_reloader(ws.serve_forever)
