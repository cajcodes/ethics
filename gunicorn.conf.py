# gunicorn.conf.py
import logging

# Gunicorn log settings
loglevel = 'info'
accesslog = 'flagged/access.log'
errorlog = 'flagged/error.log'

# Custom log format
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Setup logging
logger = logging.getLogger('gunicorn.error')
logger.setLevel(loglevel.upper())

# Other Gunicorn settings
workers = 4
bind = '0.0.0.0:8000'
