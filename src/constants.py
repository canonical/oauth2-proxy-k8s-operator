# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charmed oauth2-proxy's constant variables."""

import string
from pathlib import Path

# Application constants
WORKLOAD_CONTAINER = "oauth2-proxy"
WORKLOAD_SERVICE = "oauth2-proxy"
OAUTH2_PROXY_API_PORT = 4180
OAUTH2_PROXY_HTTPS_PORT = 443
ACCESS_LIST_EMAILS_PATH = "/etc/config/oauth2-proxy/access_list.cfg"
CONFIG_FILE_PATH = "/etc/config/oauth2-proxy/oauth2-proxy.cfg"
COOKIES_KEY = "cookies_key"
HTTP_PROXY = "JUJU_CHARM_HTTP_PROXY"
HTTPS_PROXY = "JUJU_CHARM_HTTPS_PROXY"
NO_PROXY = "JUJU_CHARM_NO_PROXY"

# Integration constants
OAUTH_SCOPES = "openid email profile offline_access"
OAUTH_GRANT_TYPES = ["authorization_code", "refresh_token"]

AUTH_PROXY_RELATION_NAME = "auth-proxy"
FORWARD_AUTH_RELATION_NAME = "forward-auth"

PEER = "oauth2-proxy"

# Template for storing trusted certificate in a file
TRUSTED_CA_TEMPLATE = string.Template("/usr/share/ca-certificates/trusted-ca-cert-$rel_id-ca.crt")
CERT_PATHS_KEY = "provider_ca_files"

CERTIFICATES_INTEGRATION_NAME = "certificates"

SSL_CERTIFICATE = Path("/etc/ssl/certs/ca-certificates.crt")
LOCAL_CA_CERTS_PATH = Path("/usr/local/share/ca-certificates")
PRIVATE_KEY_PATH = Path("/etc/ssl/private")

CA_CERT_PATH = LOCAL_CA_CERTS_PATH / "oauth2-proxy-ca.crt"
SERVER_CERT_PATH = LOCAL_CA_CERTS_PATH / "server.crt"
SERVER_KEY_PATH = PRIVATE_KEY_PATH / "server.key"
