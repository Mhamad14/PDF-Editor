import os

# Bind to 0.0.0.0 (all interfaces) with the PORT from environment
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Worker configuration
workers = 2
timeout = 120
preload_app = True

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
