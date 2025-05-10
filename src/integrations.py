# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess
from dataclasses import dataclass, field
from typing import List

from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificateTransferRequires,
)
from charms.oauth2_proxy_k8s.v0.auth_proxy import AuthProxyProvider
from ops.charm import CharmBase

from constants import CERTIFICATES_FILE, LOCAL_CA_BUNDLE_PATH

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuthProxyIntegrationData:
    """Data source from the auth-proxy integration."""

    app_names: List[str] = field(default_factory=list)
    allowed_endpoints: List[str] = field(default_factory=list)
    headers: List[str] = field(default_factory=list)
    authenticated_emails: List[str] = field(default_factory=list)
    authenticated_email_domains: List[str] = field(default_factory=list)

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
        certs = set()
        if relation := self._charm.model.get_relation(
            self.cert_transfer_requires.relationship_name
        ):
            for unit in set(relation.units).difference([self._charm.app, self._charm.unit]):
                # Handles the case of multi-unit CA, each unit providing a different ca cert
                if cert := relation.data[unit].get("ca"):
                    certs.add(cert)

        ca_bundle = "\n".join(sorted(certs))
        with open(LOCAL_CA_BUNDLE_PATH, mode="wt") as f:
            f.write(ca_bundle)

        subprocess.run(["update-ca-certificates", "--fresh"], capture_output=True)
        self._container.push(CERTIFICATES_FILE, CERTIFICATES_FILE.read_text(), make_dirs=True)
