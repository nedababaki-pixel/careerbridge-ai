"""Gunicorn settings for CareerBridge AI (used by deploy/careerbridge.service).

Start manually with:  gunicorn -c deploy/gunicorn.conf.py app:app
"""
import multiprocessing
import os

# Only listen on localhost. Nginx is the only public entry point (ports 80 and 443).
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:8000")

# A small EC2 instance (1-2 vCPU) needs few workers. Threads let one worker wait for
# several slow AI answers at the same time without using much memory.
workers = int(os.getenv("GUNICORN_WORKERS", min(3, multiprocessing.cpu_count() + 1)))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
worker_class = "gthread"

# The app waits up to 10 s (connect) + 90 s (read) for Gemini, so the worker timeout
# must be longer. The original default (30 s) killed slow requests and caused 502 errors.
timeout = 120
graceful_timeout = 30
keepalive = 5

# Recycle workers now and then to keep memory use stable.
max_requests = 500
max_requests_jitter = 50

# Logs go to stdout/stderr, which systemd sends to the journal (journalctl -u careerbridge).
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
# The access log never includes request bodies, so CV text is not logged.
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms'
