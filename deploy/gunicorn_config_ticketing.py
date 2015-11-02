import multiprocessing

bind = "unix:/run/www-sockets/www-ticketing/ticketing.sock"
pidfile = "/run/www-sockets/www-ticketing/ticketing.pid"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "gevent"
syslog = True
syslog_facility = "local5"
pythonpath = 'deploy'
