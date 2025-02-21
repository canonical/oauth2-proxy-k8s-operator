# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed oauth2-proxy's constant variables."""

# Application constants
WORKLOAD_CONTAINER = "oauth2-proxy"
WORKLOAD_SERVICE = "oauth2-proxy"
OAUTH2_PROXY_API_PORT = 4180
ACCESS_LIST_EMAILS_PATH = "/etc/config/oauth2-proxy/access_list.cfg"
CONFIG_FILE_PATH = "/etc/config/oauth2-proxy/oauth2-proxy.cfg"
COOKIES_KEY = "cookies_key"
HTTP_PROXY = "JUJU_CHARM_HTTP_PROXY"
HTTPS_PROXY = "JUJU_CHARM_HTTPS_PROXY"
NO_PROXY = "JUJU_CHARM_NO_PROXY"

# Integration constants
OAUTH_SCOPES = "openid email profile offline_access"
OAUTH_GRANT_TYPES = ["authorization_code", "refresh_token"]

PEER = "oauth2-proxy"
