# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import ipaddress
import logging
import subprocess
from contextlib import suppress
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urlparse

from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificateTransferRequires,
)
from charms.oauth2_proxy_k8s.v0.auth_proxy import AuthProxyProvider
from charms.tls_certificates_interface.v4.tls_certificates import (
    CertificateRequestAttributes,
    Mode,
    ProviderCertificate,
    TLSCertificatesRequiresV4,
)
from ops.charm import CharmBase
from ops.pebble import PathError
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from constants import (
    CA_CERT_PATH,
    CERT_PATHS_KEY,
    CERTIFICATES_INTEGRATION_NAME,
    SERVER_CERT_PATH,
    SERVER_KEY_PATH,
    SSL_CERTIFICATE,
    TRUSTED_CA_TEMPLATE,
)
from exceptions import CertificatesError

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


class CertificatesIntegration:
    def __init__(self, charm: CharmBase) -> None:
        self._charm = charm
        self._container = charm._container

        k8s_svc_host = charm._sans_dns
        sans_dns, sans_ip = [k8s_svc_host], []

        if ingress_url := charm.ingress.url:
            ingress_domain = urlparse(ingress_url).netloc

            try:
                ipaddress.ip_address(ingress_domain)
            except ValueError:
                sans_dns.append(ingress_domain)
            else:
                sans_ip.append(ingress_domain)

        self.csr_attributes = CertificateRequestAttributes(
            common_name=k8s_svc_host,
            sans_dns=frozenset(sans_dns),
            sans_ip=frozenset(sans_ip),
        )
        self.cert_requirer = TLSCertificatesRequiresV4(
            charm,
            relationship_name=CERTIFICATES_INTEGRATION_NAME,
            certificate_requests=[self.csr_attributes],
            mode=Mode.UNIT,
            refresh_events=[
                charm.ingress.on.ready,
                charm.ingress.on.revoked,
            ],
        )

    @property
    def _ca_cert(self) -> Optional[str]:
        return str(self._certs.ca) if self._certs else None

    @property
    def _server_key(self) -> Optional[str]:
        private_key = self.cert_requirer.private_key
        return str(private_key) if private_key else None

    @property
    def _server_cert(self) -> Optional[str]:
        return str(self._certs.certificate) if self._certs else None

    @property
    def _certs(self) -> Optional[ProviderCertificate]:
        cert, *_ = self.cert_requirer.get_assigned_certificate(self.csr_attributes)
        return cert

    def update_certificates(self) -> None:
        if not self._charm.model.get_relation(CERTIFICATES_INTEGRATION_NAME):
            logger.debug("The certificates integration is not ready.")
            self._remove_certificates()
            return

        if not self.certs_ready():
            logger.debug("The certificates data is not ready.")
            self._remove_certificates()
            return

        self._prepare_certificates()
        self._push_certificates()

    def certs_ready(self) -> bool:
        certs, private_key = self.cert_requirer.get_assigned_certificate(self.csr_attributes)
        return all((certs, private_key))

    def _prepare_certificates(self) -> None:
        CA_CERT_PATH.write_text(self._ca_cert)
        SERVER_KEY_PATH.write_text(self._server_key)
        SERVER_CERT_PATH.write_text(self._server_cert)

        try:
            for attempt in Retrying(
                wait=wait_fixed(3),
                stop=stop_after_attempt(3),
                retry=retry_if_exception_type(subprocess.CalledProcessError),
                reraise=True,
            ):
                with attempt:
                    subprocess.run(
                        ["update-ca-certificates", "--fresh"],
                        check=True,
                        text=True,
                        capture_output=True,
                    )
        except subprocess.CalledProcessError as e:
            logger.error(e.stderr)
            raise CertificatesError("TLS certificates update failed")

    def _push_certificates(self) -> None:
        self._container.push(SSL_CERTIFICATE, SSL_CERTIFICATE.read_text(), make_dirs=True)
        self._container.push(CA_CERT_PATH, self._ca_cert, make_dirs=True)
        self._container.push(SERVER_KEY_PATH, self._server_key, make_dirs=True)
        self._container.push(SERVER_CERT_PATH, self._server_cert, make_dirs=True)

    def _remove_certificates(self) -> None:
        for file in (SSL_CERTIFICATE, CA_CERT_PATH, SERVER_KEY_PATH, SERVER_CERT_PATH):
            with suppress(PathError):
                self._container.remove_path(file)


class TrustedCertificatesTransferIntegration:
    def __init__(self, charm: CharmBase):
        self._charm = charm
        self._container = charm._container
        self._peers = charm._peers
        self.cert_transfer_requires = CertificateTransferRequires(charm, relationship_name="receive-ca-cert")

    def update_trusted_ca_certs(self) -> None:
        """Receive trusted certificates from the certificate_transfer integration.

        This function is needed because relation events are not emitted on upgrade,
        and because there is no persistent storage for certs.
        """
        if not self._charm.model.get_relation(relation_name=self.cert_transfer_requires.relationship_name):
            logger.warning(
                "Missing certificate_transfer integration, OAuth2 Proxy will skip validation of certificates presented when using HTTPS providers. Don't do this in production"
            )
            return

        logger.info(
            "Pulling trusted ca certificates from %s relation.",
            self.cert_transfer_requires.relationship_name,
        )
        certs = []
        for relation in self._charm.model.relations.get(self.cert_transfer_requires.relationship_name, []):
            for unit in set(relation.units).difference([self._charm.app, self._charm.unit]):
                cert_path = TRUSTED_CA_TEMPLATE.substitute(rel_id=relation.id)
                if cert := relation.data[unit].get("ca"):
                    self._container.push(cert_path, cert, make_dirs=True)
                    certs.append(cert_path)

        self._peers.data[self._charm.app][CERT_PATHS_KEY] = str(certs)

        subprocess.run(["update-ca-certificates", "--fresh"])
