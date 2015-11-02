Administration
==============

``bin/user_info.py``
--------------------

…was the single most useful file I wrote.

Processing payments
-------------------

You should have the treasurer run off a CSV of the recent transactions fairly regularly. You’ll then need to cut it down to only include the rows since the last run, and then pass it to ``bin/load_payments.py``.

Load payments produces a log file for the run, and a “rejects” file for lines which it failed to process. You then need to inspect those and figure out which people have failed to set the right reference, etc.

The email daemon will automatically send out “you have paid, thanks” emails as ``load_payments.py`` makes changes to the database.

Miscellaneous admin scripts
---------------------------

``bin`` contains various scripts to do “things”. I haven’t documented them fully—read them before using them! Hopefully some will be useful to you.

Why do these scripts take a list of IDs in a CSV, rather than working it out for themselves?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

I kept having exceptions and special cases which meant running a query to say, purge unpaid tickets, was infeasible/dangerous/a bad idea. Therefore, the workflow was roughly

* run something in ``queries/`` to produce a CSV of people matching certain criteria
* open that up in Google Drive and check it over
* delete everything but the first (or first two—see below) columns, save that as a CSV
* run the relevant script over that file

First two: if possible (say, if specifying user_id/ticket_id is applicable), this serves as a safeguard against mistakes, since the script in ``bin`` will check that the user_id matches the ticket specified.

For example,

* ``$ psql ticketing < queries/unpaid.csv``
* open it up, select rows that are past the deadline, remove special cases…
* delete all but the first two columns; save that as a CSV
* run ``bin/purge.py`` over the result.

Common (by-hand) admin tasks
----------------------------

E.g., removing a ticket someone created by accident…

.. code-block:: sql

    UPDATE tickets SET finalised=NULL, expires=utcnow(), expires_reason='admin-intervention' WHERE ticket_id=M AND user_id=N

…or re-sending the receipt email after making some modifications/corrections

.. code-block:: sql

    UPDATE users SET last_receipt=NULL WHERE user_id=N

“Current ticket counts”
-----------------------

The “admin” app currently serves one purpose: it shows some charts and numbers, the current sold-tickets counts, protected by Raven.
