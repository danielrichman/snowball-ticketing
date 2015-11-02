Preface
=======

I’ve separated my handover information into not-quite-“documentation” for the code I’ve written, and general chat about stuff I did. You are reading the former. Since it applies to code which may be re-used, it may (hopefully) be useful next year (until someone replaces my mess).

Updating the documentation
--------------------------

This is “correct” as of March 2014 (and was written by Daniel Richman, the webmaster of Snowball 2013). Hopefully it will be updated as others modify the code, but, be warned.

History
-------

When I took over in 2013, the existing order system was written in PHP and hosted on the SRCF. My creation is heavily influenced by it (which features to include/omit, etc.). It had some flaws (SQL injection everywhere), didn’t support sales to Alumni, and didn’t use Raven (authentication done by emailing a secret to a cam address). I therefore decided to create something from scratch; this is the result. It’s certainly not perfect, but I’d like to think improved things a bit. (That said, the PHP system did work and is still available for use.)

Why Flask?
----------

The fact that I wanted to have dual Raven and password (for Alumni) authentication meant that I was reluctant to use say, Django, since I was worried that I would have to spend too long wrestling / figuring out how to customise its auth bits. In the end, I probably spent equal amounts of time re-inventing the wheel.

Flask is super-lightweight and quick to get started with, does a lot of the boring things for you but (notably) does not provide an ORM…

Lack of an ORM
--------------

…that’s not to say that one can’t use an ORM with flask (say SqlAlchemy). My choosing to not use an ORM was basically a poor choice. The only argument I have *for* what I've done is that a few of the custom queries are quite carefully optimised for speed (e.g., counting up the tickets—a query that is executed on quite a few page loads) and/or to avoid race conditions (especially important on the launch day rush). I spent a lot of time re-inventing the wheel as result of doing this.

Bugs?
-----

The website launched with one actual “bug”: I forgot to pass the “switch on UTF8” flag to postgres in the daemon that sends emails, so one person’s email had to be re-sent.

Besides that, there were a couple of… design flaws, which you may or may not like to attempt to fix:

* After buying a ticket, you’re sent back to the homepage, which has since been updated with “how to pay”, a list of your tickets & their status, … Originally, it did not have the green “success” box, and a lot of people interpreted this as a “confirm” step, clicking the “Buy tickets” button again (which was present in case someone wanted to buy *more* tickets). The green box was quickly hacked on as a result.

* VIP and Standard tickets are separate and have separate waiting lists. The VIP waiting list barely shifted at all so, (if I hadn’t intervened) those joining the VIP waiting list would have been quite liable to not get any tickets at all.

  The “workaround” was that I told those that wanted to join the VIP waiting list to also buy (& indeed, pay for) a standard ticket, which we’d then upgrade. (I added a notice to the site, and ran a query to check for people on the VIP waiting list but without normal tickets—see ``../queries/vip_wl_no_standard.sql``.)
  
  In hindsignt, I probably wanted tickets to have 4 states: waiting, standard, standard & waiting for VIP. If you want to implement this…

A minor issue: MUAs automatically detect and highlight links in plain text emails, however, they will typically not include a trailing period. There is a 1 in 64 chance that the routine that generates secrets for email confirmation, password reset etc. will put a period at the end of the secret—breaking this.

Contact
-------

If you want to get in touch with me, email would be best main@danielrichman.co.uk, and I’m generally happy to (try and) help (though perhaps not at short notice!).
