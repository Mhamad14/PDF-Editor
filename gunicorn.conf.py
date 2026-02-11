import os

# Bind to 0.0.0.0 (all interfaces) with the PORT from environment
port = os.environ.get("PORT", "10000")
bind = f"0.0.0.0:{port}"

# Worker configuration - single worker to reduce memory on Railway hobby tier
workers = 1
timeout = 120

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
