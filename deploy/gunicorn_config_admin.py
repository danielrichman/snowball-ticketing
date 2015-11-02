import multiprocessing

bind = "unix:/run/www-sockets/www-ticketing/admin.sock"
pidfile = "/run/www-sockets/www-ticketing/admin.pid"
workers = 1
syslog = True
syslog_facility = "local5"
pythonpath = 'deploy'
