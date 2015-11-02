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

"""payments - parsing the bank statements"""

from __future__ import unicode_literals, print_function

import sys
import os.path
import csv
import re
from decimal import Decimal
from datetime import datetime
import traceback
import logging

import psycopg2

from .. import utils, users, tickets


logger = utils.getLogger(__name__)

_expect_headings = ["Transaction Date", "Transaction Type", "Sort Code",
    "Account Number", "Transaction Description", "Debit Amount",
    "Credit Amount", "Balance", ""]
_expect_account = ("'12-34-56", "12345678")
_reference_re = re.compile(r"^[A-Za-z0-9]{3,}/[0-9]{4,}$")


class StatementError(ValueError):
    """
    Error processing a line from a statement
    
    .. attribute what::

        Which value was bad

    .. attribute actual::

        The value of the bad column

    .. attribute expected::

        Optionally, the value expected
    
    """
    def __init__(self, what, actual, expected=None):
        super(StatementError, self).__init__(what, actual, expected)
        self.what = what
        self.actual = actual
        self.expected = expected
    def __str__(self):
        s = "StatementError: bad {0}: {1!r}".format(self.what, self.actual)
        if self.expected is not None:
            s += "; expected {0!r}".format(self.expected)
        return s

class SkipLine(Exception):
    """We are not interested in this line from the statement"""


def main(filename, dry_run, postgres_settings):
    """
    The main method of the payment processing script
    
    * Connects to postgres using `postgres_settings`
    * Reads statement rows from `filename`
    * Processes good rows
    * If `dry_run` is ``True``, does not make any actual changes
    * Writes rejected rows to ``filename + ".rejects"``, which must not exist
    * Writes a log to ``filename + ".log"``, which must not exist
    """

    rejects_filename = filename + ".rejects"
    log_filename = filename + ".log"

    if os.path.exists(rejects_filename):
        raise IOError("rejects file already exists")
    if os.path.exists(log_filename):
        raise IOError("log file already exists")

    formatter = logging.Formatter("%(levelname)s: %(message)s")
    handler = logging.FileHandler(log_filename)
    handler.setFormatter(formatter)
    handler.setLevel(logging.DEBUG)

    logger = logging.getLogger()
    logger.setLevel(min(logging.DEBUG, logger.level))

    try:
        logger.addHandler(handler)

        pg = psycopg2.connect(connection_factory=utils.PostgreSQLConnection,
                              **postgres_settings)

        with open(filename) as statement, open(rejects_filename, "a") as rejects:
            process_statement(statement, rejects, dry_run, pg)

    finally:
        logger.removeHandler(handler)

def process_statement(statement_file, rejects_file, dry_run, pg):
    """
    parse a statement csv from file `f`

    The first line must contain the headings.

    yields values from :func:`parse_statement_line`
    """

    reader = csv.reader(statement_file)
    headings = reader.next()

    if headings != _expect_headings:
        raise StatementError("headings", headings, _expect_headings)

    rejects = csv.writer(rejects_file)
    rejects.writerow(headings[:-1] + ["error"])

    for row in reader:
        try:
            amount, reference, meta = parse_statement_line(row)
            user = identify_user(reference, pg=pg)
            process_payment(user, amount, meta, dry_run, pg=pg)
        except StatementError as e:
            logger.debug("rejecting statement line %r", row, exc_info=True)
            rejects.writerow(row + [str(e)])
        except SkipLine as e:
            logger.debug("skipping statement line %r", row)
            rejects.writerow(row + ["uninterested"])
        else:
            logger.debug("successfully processed line %r", row)

def parse_statement_line(row):
    """
    parse a statement csv from file `f`

    The first line must contain the headings.

    returns ``credit_amount_pence, reference, meta``, where `meta` is a
    :class:`dict` with elements:
    * date (received)
    * description (string)
    ... if the line represents an incoming payment, and ``False`` otherwise.
    """

    date, type, sort_code, account_number, description, \
            debit_amt, credit_amt, balance = row

    account = (sort_code, account_number)
    if account != _expect_account:
        raise StatementError("account", account, _expect_account)

    # transfer; faster payments in (presumably); deposits
    if type not in ("TFR", "FPI", "DEP"):
        raise SkipLine("type: " + type)

    if debit_amt != "":
        raise StatementError("debit amt", debit_amt, "")
    if credit_amt == "":
        raise StatementError("credit amt", credit_amt)

    date = datetime.strptime(date, "%d/%m/%Y").date()

    for word in description.split():
        if _reference_re.match(word):
            reference = word
            break
    else:
        raise StatementError("description", description)

    credit_amt = int(Decimal(credit_amt) * 100)

    meta = {"date": date, "description": description}
    logger.debug("Parsed transfer: date=%s reference=%r "
                 "amt=%s description=%r",
                 date, reference, credit_amt, description)

    return credit_amt, reference, meta

def identify_user(reference, pg):
    """
    Attempt to identify a user from their reference
    
    Returns the user (:class:`dict`) or raises :exc:`StatementError`
    """
    ref_string, _, user_id = reference.partition("/")
    if _ != "/":
        raise StatementError("reference", reference)

    try:
        user_id = int(user_id)
    except ValueError:
        raise StatementError("reference", reference)

    try:
        user = users.get_user(user_id, pg=pg)
    except users.NoSuchUser:
        raise StatementError("user_id", user_id)

    expect_reference = tickets.reference(user)
    if reference.lower() != expect_reference.lower():
        raise StatementError("reference", reference, expect_reference)

    # close the transaction (we didn't do anything anyway)
    pg.commit()

    return user_id

def process_payment(user_id, amount, meta, dry_run, pg):
    """
    Mark the tickets of `user_id` paid, providing `amount` is correct

    ... i.e., provided their :func:`tickets.outstanding_balance` matches
    `amount`.

    Adds a description of the payment to the tickets' `notes` (info from
    `meta`).

    Raises :exc:`StatementError` if something is wrong.

    Performs all checks but no modifications if `dry_run` is ``True``.
    """

    # ensure that the .rollback() in except: doesn't destroy anything
    assert pg.get_transaction_status() == \
            psycopg2.extensions.TRANSACTION_STATUS_IDLE

    try:
        tickets.user_pg_lock(user_id, pg=pg)

        expect_amt, ticket_ids = \
                tickets.outstanding_balance(user_id, ids_too=True, pg=pg)
        if expect_amt != amount:
            raise StatementError("amount", amount, expect_amt)

        logger.info("Successful payment of %s for tickets %r (%r)",
                    amount, ticket_ids, meta["description"],
                    extra={"user_id": user_id})

        add_note = "paid:\n" \
                   "    script ran on {now}\n" \
                   "    bank date: {meta[date]}\n" \
                   "    amount: {amount}\n" \
                   "    tickets: {ticket_ids!r}\n" \
                   "    description {meta[description]!r}\n" \
                   .format(now=datetime.utcnow(), meta=meta, amount=amount,
                           ticket_ids=ticket_ids)

        if not dry_run:
            tickets.mark_paid(ticket_ids, add_note=add_note, pg=pg)

    except:
        logger.debug("rolling back")
        pg.rollback()
        raise
    else:
        logger.debug("committing")
        pg.commit()
