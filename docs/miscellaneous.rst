Overview & miscellaneous bits
=============================

There’s no real order to this; just…bits of information

Dependencies etc.
-----------------

The lookup service can take up to a second to reply sometimes (or at least, we give up after a second, and occasionally hit that limit). To avoid locking up the app process during that time, I’ve swapped to gevent’s HTTP client in the :mod:`snowball_ticketing.lookup.connection` module, and am using the gunicorn gevent worker.

This (unfortunately ☹) confines us to using Python 2 (for now).

I’ve been using `virtualenv <http://www.virtualenv.org/>`_ to keep dependencies, so you may need to ``source venv/bin/activate`` before running anything.

.. seealso:: ``dependencies`` (lesscss, coffeescript, libyaml-dev)
.. seealso:: ``requirements.txt`` (Python dependencies)

Coffeescript & LESSCSS
----------------------

…are quite convenient. The sources are in ``coffee/`` and ``less/``, and are compiled by running ``make``, which places the output in ``static/``, ready for use.

Templates & theming
-------------------

Before the web design was finalised, I developed using a bland plain template, later swapping out “base.html” etc. with the final design. This does however mean that the bland template still works—you can swap back to it by linking the right directory to ``templates/theme/``. Moreover, I hope this will make it easy for you to “theme” the ticketing system, if you choose to go to that effort.

The templates are based on `Bootstrap 2 <http://getbootstrap.com>`_. If you want to theme it, you’ll probably need to build your design using Bootstrap 2. Note that instead of applying several classes to elements, where possible, I’ve used mixins. This is admittedly a less common way to use bootstrap, and has some quirks.

Database miscellanea
--------------------

(Obviously) events such as “finalised” and “paid” are represented as timestamp column; “NULL” represents “not paid” (etc.); a non-null value represents “has paid, and the time they paid was…”

(Perhaps less obviously) for the “expired” column in the tickets table:

* “NULL” represents “will never expire”,
* a value in the past represents “expired”,
* a value in the future represents “will expire at this time”.

Buying tickets: overview
------------------------

* Customer logs in
* Customer is presented with two buttons: “buy standard tickets” and “buy vip tickets”, which will be coloured (or disabled) depending on whether either type has gone to the waiting list, sold out, not yet released…
* Clicking buy tickets inserts rows into the “tickets” table, with the “finalised” column NULL, and the “expires” column set to ten minutes time. Crucially, “unfinalised” tickets contribute towards the count of sold tickets.
* The customer is sent to the “details” page, which provides a form to put names, etc. on the unfinalised tickets; submitting the form finalised them. The act of doing this clears the “expires” column.
* Customer is sent back to the homepage. The homepage now lists their tickets, payment info, etc.

The idea behind the “unfinalised” thing is so that people can reserve tickets and then get time to put names on them. On reviewing the logs, this was probably completely unnecessary, since tickets don’t sell out remotely quickly enough for this to be a problem. I implemented this because the previous system did.

The details page will of course not finalise tickets if invalid data is provided. It will, however, finalise a subset of the tickets if only invalid data is provided for the others.

Confirmation Emails
-------------------

We want to send a confirmation email once someone has reserved tickets. It would be a bit odd to send a “you’ve reserved these tickets” and then another email when they’ve put names on them. Moreover, if they finalise a few of their tickets due to invalid info on the details form, we don’t want to produce an email until they’ve finalised the rest.

Suppose, then that finalised emails were sent by “details” view, and only once all tickets were finalised. If someone finalised only some of their tickets, and then the others expired, they’d never get an email. Hence, instead, a daemon handles sending receipt mails. It looks for someone with no unfinalised tickets, that hasn’t had a receipt since the last change (finalisation or payment) to their tickets, and mails them one.

Ticket limits
-------------

Sales are controlled by the ``tickets_settings`` table.

There are three types of condition it sets

* are tickets “not-yet-open”, “available” or “closed”?
* is there a quota on how many can be sold? has it been met?
* is there a quota on the waiting list? has it been met?

“available” AND quota_met AND waiting_quota_met is equivalent to “closed”; see :func:`snowball_ticketing.tickets.views.home` “pseudo-modes”.

Rationale for “quota_met” boolean:
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Suppose:

* person A buys the last 4 tickets
* person B then has to go on the waiting list
* ten minutes later, A has not finalised their tickets and so they expire
* person C coould now come and buy those 4 tickets, jumping B in the queue

Therefore, as soon as we `meet` the quota, the “quota_met” column is set, and people are redirected to the waiting list.

.. seealso:: :func:`snowball_ticketing.tickets.set_quota_met`

Barcodes
--------

…are produced by ``bin/ticket_labels.py``.

I fed them into the right hand fold out manual feed tray of the Library Printers; face down, long edge into printer. Some effort was required to get it to print at the right scale; notably Google Chrome’s PDF printer seems to want to try and fit the PDF to A4 paper and ever so slightly shrinks it. I (sorry) had to use Adobe Reader to print it (choose portrait, “Actual size”, untick “both sides”; printer properties: bypass tray, “thick 1”, manual 100% zoom).

Deployment
----------

The app is run in gunicorn (gevent workers—see above). Processes are started by supervisord (see ``deploy/supervisor.conf``); nginx then proxies non-static-file requests to it (see ``deploy/nginx.conf``). Cron runs the receipt-email-daemon periodically (``deploy/crontab``).

The “info” pages (homepage, committee, enternatinment information, …) are “pre-rendered” by ``bin/prerender.py``, and then nginx will serve those files as static, if they exist.

.. seealso:: :func:`snowball_ticketing.info.prerender` and ``deploy/nginx.conf``.

Development servers
~~~~~~~~~~~~~~~~~~~

Running ``bin/debug_app_ticketing.py`` or ``bin/debug_app_admin.py`` will start a development server using the database ``ticketing-test`` (as opposed to ``ticketing``, the live database).

Logging
-------

Logs are written to

* syslog LOCAL5 (see /etc/rsyslog.conf),
* SMTP (critical errors only),
* the `log` table: crucially, tags log entries with the user and session id, allowing ``bin/user_info.py`` to retrieve it.
  
.. warning:: Careful! Emails on errors is quite a dangerous thing to do (traffic amplification attack if done incorrectly; the UCS will be very unhappy if you flood yourself with mail…); even bad practice. Your call.

Notes columns and the log table
-------------------------------

The users and tickets tables have notes columns—I used this to keep track of (the many) special cases; some scripts add to the columns, and we had the laptops on the door display the contents.
