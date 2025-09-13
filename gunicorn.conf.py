bind = "0.0.0.0:5000"
workers = 1
worker_class = "sync"
timeout = 600  # 10 minutes
keepalive = 2
max_requests = 1000
reload = True
