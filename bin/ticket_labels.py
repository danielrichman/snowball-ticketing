from __future__ import unicode_literals, print_function

import sys
import os

root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, root)

import itertools

import psycopg2
from reportlab.pdfgen import canvas
from reportlab.lib import pagesizes, units, colors
from reportlab.graphics.barcode import code128

from snowball_ticketing import utils

def main():
    conn = psycopg2.connect(dbname="ticketing",
                            connection_factory=utils.PostgreSQLConnection)
    c = canvas.Canvas("barcodes.pdf", pagesize=pagesizes.A4)
    render(c, pg=conn)
    c.save()
    conn.close()

def render(canvas, bounding_box=False, pg=None):
    assert canvas._pagesize == pagesizes.A4

    # query setup
    query = "SELECT othernames, surname, ticket_id, vip " \
            "FROM tickets " \
            "WHERE paid IS NOT NULL AND" \
            "   printed IS NULL " \
            "ORDER BY user_id, surname, othernames"

    cur = pg.cursor(True)
    cur.execute(query)

    # constants
    start = (11.93 * units.mm, 24 * units.mm)
    size = (41 * units.mm, 17.5 * units.mm)
    delta = (48.35 * units.mm, 21.2 * units.mm)
    count = (4, 12)

    bar_height = size[1] / 4.0 - 1 * units.mm
    bar_width = 0.71 * units.mm

    coord_positions = [[start[n] + i * delta[n]
                        for i in range(count[n])]
                       for n in (0, 1)]

    ticket_types = {
        True: {"entry_time": "8:00pm", "type_string": "VIP"},
        False: {"entry_time": "8:30pm", "type_string": "Standard"}
    }

    # position iterator stuff
    positions = list(itertools.product(*coord_positions))
    pos_enum = itertools.cycle(range(len(positions)))

    # page counting
    per_page = count[0] * count[1]
    pages = cur.rowcount // per_page
    if cur.rowcount % per_page:
        pages += 1

    page = 0

    # util
    def centred_text(canvas, x, y, row, what):
        x_centre = x + size[0] / 2.0
        canvas.saveState()

        for font_size in range(12, 5, -1):
            canvas.setFontSize(font_size)
            if canvas.stringWidth(what) < size[0]:
                break
        else:
            print("Warning: text", what, "too wide")

        offset = row * size[1] / 4.0
        canvas.drawCentredString(x_centre, y + offset, what)
        canvas.restoreState()

    # go
    for pos_n, ticket in itertools.izip(pos_enum, cur):
        if pos_n == 0:
            if page != 0:
                canvas.showPage()

            page += 1

            footer = "Barcodes page {0} of {1}".format(page, pages)
            canvas.drawCentredString(pagesizes.A4[0] / 2.0, 20, footer)

        ticket.update(ticket_types[ticket["vip"]])
        name = "{othernames} {surname}".format(**ticket)
        barcode_value = "{ticket_id:04d}".format(**ticket)
        num_type = "{ticket_id:04d}      {type_string}".format(**ticket)
        entry_time = "Entry time: {entry_time}".format(**ticket)

        x, y = positions[pos_n]

        barcode = code128.Code128(barcode_value,
                                  barWidth=bar_width,
                                  barHeight=bar_height,
                                  quiet=False)
        x_offset = (size[0] - barcode.width) / 2
        if x_offset < 0:
            raise ValueError("barcode too wide")
        barcode.drawOn(canvas, x + x_offset, y + 2 * size[1] / 4.0)

        centred_text(canvas, x, y, 3, name)
        centred_text(canvas, x, y, 1, num_type)
        centred_text(canvas, x, y, 0, entry_time)

        if bounding_box:
            canvas.setStrokeColor(colors.red)
            canvas.rect(x, y, size[0], size[1], stroke=1, fill=0)
            canvas.setStrokeColor(colors.black)

    # last page
    canvas.showPage()

    # cleanup
    cur.close()

if __name__ == "__main__":
    main()
