import sys
import os
import logging
import functools

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

from snowball_ticketing.apps.ticketing import app
from snowball_ticketing.info import prerender

logging.basicConfig(level=logging.DEBUG)
prerender(app)
