# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed oauth2-proxy's constant variables."""

from pathlib import Path

# Charm constants
PEBBLE_READY_CHECK_NAME = "ready"

# Application constants
WORKLOAD_CONTAINER = "oauth2-proxy"
WORKLOAD_SERVICE = "oauth2-proxy"
OAUTH2_PROXY_API_PORT = 4180
ACCESS_LIST_EMAILS_PATH = "/etc/config/oauth2-proxy/access_list.cfg"
COOKIE_SECRET_KEY = "cookies_key"
HTTP_PROXY = "JUJU_CHARM_HTTP_PROXY"
HTTPS_PROXY = "JUJU_CHARM_HTTPS_PROXY"
NO_PROXY = "JUJU_CHARM_NO_PROXY"

# Integration constants
OAUTH_SCOPES = "openid email profile offline_access"
OAUTH_GRANT_TYPES = ["authorization_code", "refresh_token"]

AUTH_PROXY_RELATION_NAME = "auth-proxy"
FORWARD_AUTH_RELATION_NAME = "forward-auth"
PEER_INTEGRATION_NAME = "oauth2-proxy"

CERTIFICATES_PATH = Path("/etc/ssl/certs")
CERTIFICATES_FILE = Path(CERTIFICATES_PATH / "ca-certificates.crt")
LOCAL_CA_BUNDLE_PATH = Path("/usr/local/share/ca-certificates/ca-certificates.crt")
