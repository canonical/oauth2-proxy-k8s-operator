#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import os
import secrets
from typing import Optional
from urllib.parse import urlparse

from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificatesAvailableEvent,
    CertificatesRemovedEvent,
)
from charms.hydra.v0.oauth import ClientConfig as OauthClientConfig
from charms.hydra.v0.oauth import OAuthInfoChangedEvent, OAuthRequirer
from charms.oauth2_proxy_k8s.v0.auth_proxy import (
    AuthProxyConfigChangedEvent,
    AuthProxyConfigRemovedEvent,
    AuthProxyProvider,
)
from charms.oauth2_proxy_k8s.v0.forward_auth import (
    ForwardAuthConfig,
    ForwardAuthProvider,
    ForwardAuthProxySet,
    ForwardAuthRelationRemovedEvent,
    InvalidForwardAuthConfigEvent,
)
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from jinja2 import Template
from ops import main, pebble
from ops.charm import CharmBase, ConfigChangedEvent, HookEvent, PebbleReadyEvent, UpdateStatusEvent
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    Relation,
    WaitingStatus,
)
from ops.pebble import ChangeError, CheckStatus, Layer

from cli import CommandLine
from constants import (
    ACCESS_LIST_EMAILS_PATH,
    AUTH_PROXY_RELATION_NAME,
    CONFIG_FILE_PATH,
    COOKIES_KEY,
    FORWARD_AUTH_RELATION_NAME,
    HTTP_PROXY,
    HTTPS_PROXY,
    NO_PROXY,
    OAUTH2_PROXY_API_PORT,
    OAUTH_GRANT_TYPES,
    OAUTH_SCOPES,
    PEER,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from integrations import AuthProxyIntegrationData, TrustedCertificatesTransferIntegration
from log import log_event_handler

logger = logging.getLogger(__name__)


class Oauth2ProxyK8sOperatorCharm(CharmBase):
    """Charmed Oauth2-Proxy."""

    def __init__(self, *args) -> None:
        super().__init__(*args)

        self._container = self.unit.get_container(WORKLOAD_CONTAINER)
        self.cli = CommandLine(self._container)

        self.ingress = IngressPerAppRequirer(
            self,
            relation_name="ingress",
            port=OAUTH2_PROXY_API_PORT,
            strip_prefix=True,
            redirect_https=False,
        )

        self.trusted_cert_transfer = TrustedCertificatesTransferIntegration(self)

        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            WORKLOAD_CONTAINER,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        self.oauth = OAuthRequirer(self, self._oauth_client_config)

        self.auth_proxy = AuthProxyProvider(self, relation_name=AUTH_PROXY_RELATION_NAME)
        self.forward_auth = ForwardAuthProvider(
            self,
            relation_name=FORWARD_AUTH_RELATION_NAME,
            forward_auth_config=self._forward_auth_config,
        )
        self.framework.observe(self.on[WORKLOAD_CONTAINER].pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        self.framework.observe(self.on.update_status, self._on_update_status)

        # oauth integration observations
        self.framework.observe(self.oauth.on.oauth_info_changed, self._on_oauth_info_changed)
        self.framework.observe(self.oauth.on.oauth_info_removed, self._on_oauth_info_changed)

        # ingress integration observations
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

        # certificate integrations observations
        self.framework.observe(
            self.trusted_cert_transfer.cert_transfer_requires.on.certificate_set_updated,
            self._on_trusted_certificates_available,
        )
        self.framework.observe(
            self.trusted_cert_transfer.cert_transfer_requires.on.certificates_removed,
            self._on_trusted_certificates_removed,
        )

        # resource patching
        self.framework.observe(
            self.resources_patch.on.patch_failed, self._on_resource_patch_failed
        )

        # forward-auth integration observations
        self.framework.observe(
            self.forward_auth.on.forward_auth_proxy_set, self._on_forward_auth_proxy_set
        )
        self.framework.observe(
            self.forward_auth.on.invalid_forward_auth_config, self._on_invalid_forward_auth_config
        )
        self.framework.observe(
            self.forward_auth.on.forward_auth_relation_removed,
            self._on_forward_auth_relation_removed,
        )

        self.framework.observe(
            self.auth_proxy.on.proxy_config_changed, self._on_auth_proxy_config_changed
        )
        self.framework.observe(
            self.auth_proxy.on.config_removed, self._remove_auth_proxy_configuration
        )

    @property
    def _peers(self) -> Optional[Relation]:
        """Fetch the peer relation."""
        return self.model.get_relation(PEER)

    @property
    def _public_url(self) -> str:
        """Retrieve the url of the application."""
        public_endpoint = (
            self.ingress.url
            or f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{OAUTH2_PROXY_API_PORT}"
        )
        return public_endpoint

    @property
    def _public_domain(self) -> str:
        """Retrieve the url of the application."""
        url = urlparse(self._public_url)
        return url.netloc

    @property
    def _redirect_url(self) -> str:
        return os.path.join(self._public_url, "oauth2/callback")

    @property
    def _cookie_encryption_key(self) -> Optional[str]:
        """Retrieve cookie encryption key from the peer data bucket."""
        if not self._peers:
            return None
        return self._peers.data[self.app].get(COOKIES_KEY, None)

    @property
    def _oauth_client_config(self) -> OauthClientConfig:
        """OAuth client configuration."""
        return OauthClientConfig(
            self._redirect_url,
            OAUTH_SCOPES,
            OAUTH_GRANT_TYPES,
        )

    @property
    def _forward_auth_config(self) -> ForwardAuthConfig:
        auth_proxy_data = AuthProxyIntegrationData.load(self.auth_proxy)
        oauth2_proxy_url = (
            f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{OAUTH2_PROXY_API_PORT}"
        )
        return ForwardAuthConfig(
            decisions_address=oauth2_proxy_url,
            app_names=auth_proxy_data.app_names,
            headers=auth_proxy_data.headers,
        )

    @property
    def _oauth2_proxy_pebble_layer(self) -> Layer:
        """OAuth2 Proxy pebble layer."""
        proxy_vars = {
            "HTTP_PROXY": HTTP_PROXY,
            "HTTPS_PROXY": HTTPS_PROXY,
            "NO_PROXY": NO_PROXY,
        }

        context = {
            "OAUTH2_PROXY_COOKIE_SECRET": self._cookie_encryption_key,
        }

        for key, env_var in proxy_vars.items():
            value = os.environ.get(env_var)
            if value:
                context.update({key: value})

        layer_config = {
            "summary": "oauth2 proxy layer",
            "services": {
                WORKLOAD_SERVICE: {
                    "summary": WORKLOAD_SERVICE,
                    "command": f"/bin/oauth2-proxy --config {CONFIG_FILE_PATH}",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": context,
                    "on-check-failure": {"up": "ignore"},
                }
            },
            "checks": {
                "up": {
                    "override": "replace",
                    "period": "10s",
                    "http": {"url": f"http://localhost:{OAUTH2_PROXY_API_PORT}/ready"},
                }
            },
        }
        return Layer(layer_config)

    @property
    def _oauth2_proxy_service_is_running(self) -> bool:
        if not self._container.can_connect():
            return False

        try:
            service = self._container.get_service(WORKLOAD_SERVICE)
        except (ModelError, RuntimeError):
            return False
        return service.is_running()

    def _validate_pebble_plan(self) -> bool:
        """Validate pebble plan."""
        try:
            plan = self._container.get_plan().to_dict()
            return bool(plan["services"][WORKLOAD_SERVICE]["on-check-failure"])
        except (KeyError, pebble.ConnectionError):
            return False

    def _render_config_file(self) -> str:
        """Render the OAuth2 Proxy configuration file."""
        oauth_integration = False
        auth_proxy_data = AuthProxyIntegrationData.load(self.auth_proxy)

        if self.oauth.is_client_created():
            oauth_provider_info = self.oauth.get_provider_info()
            oauth_integration = True

        with open("templates/oauth2-proxy.toml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            authenticated_emails_file=ACCESS_LIST_EMAILS_PATH
            if auth_proxy_data.authenticated_emails
            else None,
            authenticated_email_domains=auth_proxy_data.authenticated_email_domains,
            client_id=oauth_provider_info.client_id if oauth_integration else "default",
            client_secret=oauth_provider_info.client_secret if oauth_integration else "default",
            oauth_integration=oauth_integration,
            oidc_issuer_url=oauth_provider_info.issuer_url if oauth_integration else None,
            scopes=OAUTH_SCOPES,
            redirect_url=self._redirect_url,
            skip_auth_routes=auth_proxy_data.allowed_endpoints,
            whitelist_domains=self._public_domain,
            dev=self.config["dev"],
        )
        return rendered

    @log_event_handler(logger)
    def _on_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Handle pebble ready event.

            - open application port
            - handle status and update config
            - set workload version.

        Args:
            event: The event triggered when Pebble is ready for a workload.
        """
        self.model.unit.open_port(protocol="tcp", port=OAUTH2_PROXY_API_PORT)
        self._handle_status_update_config(event)

        if version := self.cli.get_oauth2_proxy_service_version():
            self.unit.set_workload_version(version)

    @log_event_handler(logger)
    def _on_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        """Handle ingress ready event and update oauth relation data.

        Args:
            event: The event triggered when IngressPerApp is ready.
        """
        self._handle_status_update_config(event)
        if self.unit.is_leader():
            logger.info(f"This app's ingress URL: {event.url}")
            self.oauth.update_client_config(client_config=self._oauth_client_config)

    @log_event_handler(logger)
    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        """Handle ingress revoked event and update oauth relation data.

        Args:
            event: The event triggered when IngressPerAppRevoked is emitted.
        """
        self._handle_status_update_config(event)
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")
            self.oauth.update_client_config(client_config=self._oauth_client_config)

    @log_event_handler(logger)
    def _on_trusted_certificates_available(self, event: CertificatesAvailableEvent) -> None:
        self._handle_status_update_config(event)

    @log_event_handler(logger)
    def _on_trusted_certificates_removed(self, event: CertificatesRemovedEvent) -> None:
        self._handle_status_update_config(event)

    @log_event_handler(logger)
    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Handle config-changed event."""
        self._handle_status_update_config(event)

    @log_event_handler(logger)
    def _on_update_status(self, event: UpdateStatusEvent) -> None:
        """Handle `update-status` events.

        Args:
            event: The `update-status` event triggered at intervals.
        """
        # TODO: Evaluate if this is needed
        valid_pebble_plan = self._validate_pebble_plan()
        if not valid_pebble_plan:
            self._handle_status_update_config(event)
            return

        check = self._container.get_check("up")
        if check.status != CheckStatus.UP:
            self.unit.status = MaintenanceStatus("Status check: DOWN")
            return

    @log_event_handler(logger)
    def _on_oauth_info_changed(self, event: OAuthInfoChangedEvent) -> None:
        """Handle `oauth-info-changed` event.

        Args:
            event: The `OAuthInfoChangedEvent` event triggered when integration data changed.
        """
        self._handle_status_update_config(event)

    @log_event_handler(logger)
    def _on_invalid_forward_auth_config(self, event: InvalidForwardAuthConfigEvent) -> None:
        logger.info(
            "The forward-auth config is invalid: one or more of the related apps is missing ingress relation"
        )
        self.unit.status = BlockedStatus(event.error)

    @log_event_handler(logger)
    def _on_forward_auth_proxy_set(self, event: ForwardAuthProxySet) -> None:
        logger.info("The proxy was set successfully")
        self.unit.status = ActiveStatus("OAuth2 Proxy is configured")

    @log_event_handler(logger)
    def _on_forward_auth_relation_removed(self, event: ForwardAuthRelationRemovedEvent) -> None:
        logger.info("The proxy was unset")
        # The proxy was removed, but the charm is still functional
        self.unit.status = ActiveStatus()

    @log_event_handler(logger)
    def _on_auth_proxy_config_changed(self, event: AuthProxyConfigChangedEvent) -> None:
        if not self._oauth2_proxy_service_is_running:
            self.unit.status = WaitingStatus("Waiting for OAuth2 Proxy service")
            event.defer()
            return

        self._handle_status_update_config(event)

        logger.info("Auth-proxy config has changed. Forward-auth relation will be updated")
        self.forward_auth.update_forward_auth_config(self._forward_auth_config)

    @log_event_handler(logger)
    def _remove_auth_proxy_configuration(self, event: AuthProxyConfigRemovedEvent) -> None:
        """Remove the auth-proxy-related config for a given relation."""
        self._handle_status_update_config(event)
        self.forward_auth.update_forward_auth_config(self._forward_auth_config)

    @log_event_handler(logger)
    def _handle_status_update_config(self, event: HookEvent) -> None:
        """Update the application status and configuration and restart the container.

        Args:
            event: The event triggered when the application needs to be updated.
        """
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to OAuth2-Proxy container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to OAuth2-Proxy container")
            return

        if not self._cookie_encryption_key:
            self._peers.data[self.app][COOKIES_KEY] = secrets.token_hex(16)

        self.unit.status = MaintenanceStatus("Configuring the container")

        auth_proxy_data = AuthProxyIntegrationData.load(self.auth_proxy)
        if emails := auth_proxy_data.authenticated_emails:
            users = "\n".join(emails)
            self._container.push(ACCESS_LIST_EMAILS_PATH, users, make_dirs=True)

        self.trusted_cert_transfer.update_trusted_ca_certs()

        config = self._render_config_file()
        self._container.push(CONFIG_FILE_PATH, config, make_dirs=True)

        self._container.add_layer(
            WORKLOAD_CONTAINER, self._oauth2_proxy_pebble_layer, combine=True
        )

        try:
            self._container.restart(WORKLOAD_CONTAINER)
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus(
                "Failed to restart the container, please consult the logs"
            )
            return

        self.unit.status = ActiveStatus()

    def _on_resource_patch_failed(self, event: K8sResourcePatchFailedEvent) -> None:
        logger.error(f"Failed to patch resource constraints: {event.message}")
        self.unit.status = BlockedStatus(event.message)

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        requests = {"cpu": "100m", "mem": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)


if __name__ == "__main__":  # pragma: nocover
    main.main(Oauth2ProxyK8sOperatorCharm)  # type: ignore
