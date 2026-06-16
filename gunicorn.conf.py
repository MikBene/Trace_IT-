# gunicorn.conf.py
timeout = 120  # Increase timeout to 120 seconds
workers = 2
worker_class = "sync"