import os

from decouple import config
from dotenv import load_dotenv

load_dotenv()

# Railway injects the public port in the $PORT environment variable.
# Never hardcode the listen port — honor $PORT first, then SERVICE_PORT,
# and only fall back to the original default when neither is set.
_port_raw = os.environ.get("PORT") or config("SERVICE_PORT", default="")
SERVICE_PORT = int(_port_raw) if _port_raw else 62050

# The node binds to loopback. The Marzban panel (same container) reaches it
# over 127.0.0.1 — this loopback socket is the "internal proxy" the panel
# connects to. Railway only exposes the panel's $PORT publicly.
SERVICE_HOST = config("SERVICE_HOST", default="127.0.0.1")

XRAY_API_HOST = config("XRAY_API_HOST", default="0.0.0.0")
XRAY_API_PORT = config('XRAY_API_PORT', cast=int, default=62051)
XRAY_EXECUTABLE_PATH = config("XRAY_EXECUTABLE_PATH", default="/usr/local/bin/xray")
XRAY_ASSETS_PATH = config("XRAY_ASSETS_PATH", default="/usr/local/share/xray")

# TLS for the node REST service.
# We use mutual-TLS with a shared self-signed cert: the node serves it and the
# panel presents the SAME cert as its client cert. The panel's ReSTXRayNode
# auto-fetches the server cert and supplies its own TLS cert as the client cert,
# so using one shared cert on both ends makes the handshake work with no manual
# exchange. Set SERVICE_TLS=false to disable (plain loopback — also fine inside
# the same container).
SERVICE_TLS = config('SERVICE_TLS', cast=bool, default=True)

SSL_DIR = config("SSL_DIR", default="/var/lib/marzban-node")
SSL_CERT_FILE = config("SSL_CERT_FILE", default=f"{SSL_DIR}/ssl_cert.pem")
SSL_KEY_FILE = config("SSL_KEY_FILE", default=f"{SSL_DIR}/ssl_key.pem")
# Same file as the server cert: the panel shows this exact cert as its client cert.
SSL_CLIENT_CERT_FILE = config("SSL_CLIENT_CERT_FILE", default=f"{SSL_DIR}/ssl_cert.pem")

DEBUG = config("DEBUG", cast=bool, default=False)

SERVICE_PROTOCOL = config('SERVICE_PROTOCOL', cast=str, default='rest')

# Optional inbound tag filter (comma separated). Leave empty to serve all.
INBOUNDS = config("INBOUNDS", cast=lambda v: [x.strip() for x in v.split(',')] if v else [], default="")
