# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import secrets
import subprocess
from dataclasses import dataclass, field
from typing import Any, List

from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificateTransferRequires,
)
from charms.hydra.v0.oauth import OAuthRequirer
from charms.oauth2_proxy_k8s.v0.auth_proxy import AuthProxyProvider
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from ops import Model
from ops.charm import CharmBase
from yarl import URL

from constants import (
    ACCESS_LIST_EMAILS_PATH,
    CERTIFICATES_FILE,
    COOKIE_SECRET_KEY,
    LOCAL_CA_BUNDLE_PATH,
    OAUTH2_PROXY_API_PORT,
    OAUTH_SCOPES,
    PEER_INTEGRATION_NAME,
)
from env_vars import EnvVars

logger = logging.getLogger(__name__)


class PeerData:
    def __init__(self, model: Model) -> None:
        self._model = model
        self._app = model.app

        if not self._model.get_relation(PEER_INTEGRATION_NAME):
            return

        if self._model.unit.is_leader() and self[COOKIE_SECRET_KEY] is None:
            self[COOKIE_SECRET_KEY] = secrets.token_hex(16)

    def __getitem__(self, key: str) -> Any:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return None

        def _safe_load(s):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return s  # return raw string if it's not valid JSON

        value = peers.data[self._app].get(key)
        return _safe_load(value) if value is not None else None

    def __setitem__(self, key: str, value: Any) -> None:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return

        if key == COOKIE_SECRET_KEY and self[COOKIE_SECRET_KEY] is not None:
            logger.error("Cookie secret cannot be overwritten in the peer integration")
            return

        peers.data[self._app][key] = json.dumps(value)

    def pop(self, key: str) -> Any:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return None

        data = peers.data[self._app].pop(key, None)
        return json.loads(data) if data is not None else None

    def to_env_vars(self) -> EnvVars:
        if not (cookie_secret := self[COOKIE_SECRET_KEY]):
            logger.error("Cookie secret is not found in the peer integration")
            return {}

        return {
            "OAUTH2_PROXY_COOKIE_SECRET": cookie_secret,
        }


@dataclass(frozen=True, slots=True)
class AuthProxyIntegrationData:
    """Data source from the auth-proxy integration."""

    app_names: List[str] = field(default_factory=list)
    allowed_endpoints: List[str] = field(default_factory=list)
    headers: List[str] = field(default_factory=list)
    authenticated_emails: List[str] = field(default_factory=list)
    authenticated_email_domains: List[str] = field(default_factory=list)

    def to_env_vars(self) -> EnvVars:
        env_vars = {}

        if self.allowed_endpoints:
            env_vars["OAUTH2_PROXY_SKIP_AUTH_ROUTES"] = ",".join(self.allowed_endpoints)

        if self.authenticated_emails:
            env_vars["OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE"] = ACCESS_LIST_EMAILS_PATH

        if self.authenticated_email_domains:
            env_vars["OAUTH2_PROXY_EMAIL_DOMAINS"] = ",".join(self.authenticated_email_domains)

        return env_vars

    @classmethod
    def load(cls, provider: AuthProxyProvider) -> "AuthProxyIntegrationData":
        app_names = provider.get_app_names()
        allowed_endpoints = provider.get_relations_data("allowed_endpoints")
        headers = provider.get_relations_data("headers")
        authenticated_emails = provider.get_relations_data("authenticated_emails")
        authenticated_email_domains = provider.get_relations_data("authenticated_email_domains")

        return cls(
            app_names=app_names,
            allowed_endpoints=allowed_endpoints,
            headers=headers,
            authenticated_emails=authenticated_emails,
            authenticated_email_domains=authenticated_email_domains,
        )


@dataclass(frozen=True, slots=True)
class IngressIntegrationData:
    """The data source from the ingress integration."""

    url: URL = URL()

    def to_env_vars(self) -> EnvVars:
        return {
            "OAUTH2_PROXY_REDIRECT_URL": str(self.url / "oauth2" / "callback"),
            "OAUTH2_PROXY_WHITELIST_DOMAINS": self.url.host,
        }

    @classmethod
    def load(cls, requirer: IngressPerAppRequirer) -> "IngressIntegrationData":
        model, app = requirer.charm.model.name, requirer.charm.app.name
        default_url = f"http://{app}.{model}.svc.cluster.local:{OAUTH2_PROXY_API_PORT}"
        return cls(url=URL(requirer.url or default_url))


@dataclass(frozen=True, slots=True)
class OAuthIntegrationData:
    """The data source from the oauth integration."""

    issuer_url: str = ""
    client_id: str = "default"
    client_secret: str = "default"

    def to_env_vars(self) -> EnvVars:
        return (
            {
                "OAUTH2_PROXY_CLIENT_ID": self.client_id,
                "OAUTH2_PROXY_CLIENT_SECRET": self.client_secret,
                "OAUTH2_PROXY_PROVIDER": "oidc",
                "OAUTH2_PROXY_PROVIDER_DISPLAY_NAME": "Identity Platform",
                "OAUTH2_PROXY_OIDC_ISSUER_URL": self.issuer_url,
                "OAUTH2_PROXY_SCOPE": OAUTH_SCOPES,
                "OAUTH2_PROXY_SKIP_PROVIDER_BUTTON": "true",
            }
            if self.issuer_url
            else {}
        )

    @classmethod
    def load(cls, requirer: OAuthRequirer) -> "OAuthIntegrationData":
        if not requirer.is_client_created():
            return cls()

        oauth_provider_info = requirer.get_provider_info()
        return cls(
            issuer_url=oauth_provider_info.issuer_url,
            client_id=oauth_provider_info.client_id,
            client_secret=oauth_provider_info.client_secret,
        )


class TrustedCertificatesTransferIntegration:
    def __init__(self, charm: CharmBase):
        self._charm = charm
        self._container = charm._container
        self.cert_transfer_requires = CertificateTransferRequires(
            charm, relationship_name="receive-ca-cert"
        )

    def update_trusted_ca_certs(self) -> None:
        """Receive trusted certificates from the certificate_transfer integration.

        This function is needed because relation events are not emitted on upgrade,
        and because there is no persistent storage for certs.
        """
        if not self._charm.model.get_relation(
            relation_name=self.cert_transfer_requires.relationship_name
        ):
            logger.warning(
                "Missing certificate_transfer integration, run `juju config oauth2-proxy-k8s dev=true` to skip validation of certificates presented when using HTTPS providers. Don't do this in production"
            )

        self._push_ca_certs()

    def _push_ca_certs(self) -> None:
        certs = self.cert_transfer_requires.get_all_certificates()
        ca_bundle = "\n".join(sorted(certs))

        with open(LOCAL_CA_BUNDLE_PATH, mode="wt") as f:
            f.write(ca_bundle)

        subprocess.run(["update-ca-certificates", "--fresh"], capture_output=True)
        self._container.push(CERTIFICATES_FILE, CERTIFICATES_FILE.read_text(), make_dirs=True)
