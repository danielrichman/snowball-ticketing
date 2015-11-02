import logging
import json
import sys
import gevent

import snowball_ticketing.lookup

logging.basicConfig(level=logging.DEBUG)

if len(sys.argv) != 2:
    print "Usage: {0} crsid".format(sys.argv[0])
else:
    v = snowball_ticketing.lookup.get_crsid(sys.argv[1])
    print json.dumps(v, sys.stdout, indent=4)
