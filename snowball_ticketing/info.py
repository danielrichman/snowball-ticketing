# Copyright 2013 Daniel Richman
#
# This file is part of The Snowball Ticketing System.
#
# The Snowball Ticketing System is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# The Snowball Ticketing System is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with The Snowball Ticketing System.  If not, see
# <http://www.gnu.org/licenses/>.

"""
Information

This package contains utility functions that help produce, and a Flask
blueprint containing, the static views (homepage, info about the ball, ...).

Further, the :func:`prerender` function may be used to generate the HTML that
would have been produced by those views in advance, so it may be served
directly without going via Python
"""

from __future__ import unicode_literals

import os
import os.path
import re
import functools
import yaml
import shutil

import flask
import flask.json
import jinja2
from flask import render_template, request

from . import utils

__all__ = ["bp", "prerender"]


page_filename_re = re.compile(r'^([a-zA-Z_]+)\.html$')
data_filename_re = re.compile("^([a-z]+)\.yaml$")

logger = utils.getLogger(__name__)

#: the :class:`flask.Blueprint` containing info views
bp = flask.Blueprint('info', __name__)

root_dir = os.path.join(os.path.dirname(__file__), '..')
data_dir = os.path.join(root_dir, 'data')
templates_dir = os.path.join(root_dir, 'templates')
pages_dir = os.path.join(templates_dir, 'theme', 'pages')
prerendered_dir = os.path.join(root_dir, 'prerendered')


def load_data(data_dir):
    data = {}
    for filename in os.listdir(data_dir):
        key, = data_filename_re.match(filename).groups()
        with open(os.path.join(data_dir, filename)) as f:
            data[key] = yaml.safe_load(f)
    return data

def find_pages(pages_dir):
    for page in os.listdir(pages_dir):
        match = page_filename_re.match(page)
        assert match
        yield match.groups()[0]

def setup(bp, pages):
    for endpoint in pages:
        if endpoint == 'index':
            url = "/"
        else:
            url = "/" + endpoint.replace("_", "-")
        template = "theme/pages/{0}.html".format(endpoint)
        view = functools.partial(render_template, template, **pages_data)
        bp.add_url_rule(url, endpoint, view)

    bp.add_app_template_global(pages, 'info_pages')

def prerender_pages(app, pages, output_dir):
    # Note, this assumes that it's OK for url_for to produce
    # urls rooted at /
    # Also assumes the blueprint is attached at /
    # Don't use _external!

    for filename in os.listdir(output_dir):
        if filename != '.gitignore':
            logger.debug("Cleaning %s", filename)
            os.unlink(os.path.join(output_dir, filename))
        else:
            logger.debug("Keeping .gitignore")

    with app.test_request_context():
        for endpoint in pages:
            filename = os.path.join(output_dir, endpoint + ".html")
            template = "theme/pages/{0}.html".format(endpoint)

            logger.debug("Rendering endpoint %r -> %r", endpoint, filename)
            with open(filename, "w") as f:
                f.write(render_template(template, **pages_data))

pages = list(find_pages(pages_dir))
pages_data = load_data(data_dir)
setup(bp, pages)

#: Given an app with `bp` attached, generate static info pages in prerendered/
prerender = functools.partial(prerender_pages, pages=pages,
                              output_dir=prerendered_dir)
