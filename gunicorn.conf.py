# Gunicorn configuration file
import multiprocessing

# Server socket
bind = "0.0.0.0:10000"
backlog = 2048

# Worker processes
workers = 2
worker_class = "sync"
worker_connections = 1000
timeout = 120  # Increased timeout for sync operations
keepalive = 2

# Logging
logfile = "-"
loglevel = "info"
logconfig = None

# Process naming
proc_name = "business_app"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
# keyfile = None
# certfile = None
# ssl_version = 2
# cert_reqs = 0
# ca_certs = None
# suppress_ragged_eofs = True

# Server hooks
def on_starting(server):
    pass

def on_reload(server):
    pass

def when_ready(server):
    pass

def pre_fork(server, worker):
    pass

def post_fork(server, worker):
    pass

def pre_exec(server):
    pass

def pre_request(worker, req):
    worker.log.debug("%s %s" % (req.method, req.path))

def post_request(worker, req, environ, resp):
    pass

def worker_exit(server, worker):
    pass

def nworkers_changed(server, new_value, old_value):
    pass

def on_exit(server):
    pass