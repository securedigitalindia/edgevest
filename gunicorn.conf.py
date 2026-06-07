import multiprocessing

bind             = "127.0.0.1:5555"
workers          = 2                        # trade_server is I/O-bound + SQLite; 2 is enough
worker_class     = "sync"
threads          = 4
timeout          = 60
keepalive        = 5
accesslog        = "/var/log/edgevest/access.log"
errorlog         = "/var/log/edgevest/error.log"
loglevel         = "info"
capture_output   = True
