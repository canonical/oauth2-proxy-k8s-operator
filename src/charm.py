#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import os
import secrets
from typing import Optional

from charms.hydra.v0.oauth import ClientConfig as OauthClientConfig
from charms.hydra.v0.oauth import OAuthInfoChangedEvent, OAuthRequirer
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from jinja2 import Template
from ops import main, pebble
from ops.charm import CharmBase, ConfigChangedEvent, HookEvent, PebbleReadyEvent, UpdateStatusEvent
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, Relation, WaitingStatus
from ops.pebble import ChangeError, CheckStatus, Layer

from cli import CommandLine
from constants import (
    ACCESS_LIST_EMAILS_PATH,
    CONFIG_FILE_PATH,
    COOKIES_KEY,
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
        self.oauth = OAuthRequirer(self, self._oauth_client_config)

        self.framework.observe(self.on[WORKLOAD_CONTAINER].pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        # oauth integration observations
        self.framework.observe(self.oauth.on.oauth_info_changed, self._on_oauth_info_changed)
        self.framework.observe(self.oauth.on.oauth_info_removed, self._on_oauth_info_changed)

        # ingress integration observations
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)
        self.framework.observe(self.ingress.on.revoked, self._on_ingress_revoked)

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
    def _cookie_encryption_key(self) -> Optional[str]:
        """Retrieve cookie encryption key from the peer data bucket."""
        if not self._peers:
            return None
        return self._peers.data[self.app].get(COOKIES_KEY, None)

    @property
    def _oauth_client_config(self) -> OauthClientConfig:
        """OAuth client configuration."""
        return OauthClientConfig(
            os.path.join(self._public_url, "oauth2/callback"),
            OAUTH_SCOPES,
            OAUTH_GRANT_TYPES,
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

        if self.oauth.is_client_created():
            oauth_provider_info = self.oauth.get_provider_info()
            oauth_integration = True

        with open("templates/oauth2-proxy.toml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            authenticated_emails_file=ACCESS_LIST_EMAILS_PATH if self.config["authenticated-emails-list"] else None,
            client_id=oauth_provider_info.client_id if oauth_integration else "default",
            client_secret=oauth_provider_info.client_secret if oauth_integration else "default",
            oauth_integration=oauth_integration,
            oidc_issuer_url=oauth_provider_info.issuer_url if oauth_integration else None,
            scopes=OAUTH_SCOPES,
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
        if self.unit.is_leader():
            logger.info(f"This app's ingress URL: {event.url}")
            self.oauth.update_client_config(client_config=self._oauth_client_config)

    @log_event_handler(logger)
    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        """Handle ingress revoked event and update oauth relation data.

        Args:
            event: The event triggered when IngressPerAppRevoked is emitted.
        """
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")
            self.oauth.update_client_config(client_config=self._oauth_client_config)

    @log_event_handler(logger)
    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Handle charm configuration changes.

        Args:
            event: The event triggered when the relation changed.
        """
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

        config = self._render_config_file()
        self._container.push(CONFIG_FILE_PATH, config, make_dirs=True)

        # TODO: Move `authenticated-emails-list` config to auth-proxy integration data
        if emails := self.config["authenticated-emails-list"]:
            users = "\n".join(emails.split(","))
            self._container.push(ACCESS_LIST_EMAILS_PATH, users, make_dirs=True)

        self._container.add_layer(WORKLOAD_CONTAINER, self._oauth2_proxy_pebble_layer, combine=True)

        try:
            self._container.restart(WORKLOAD_CONTAINER)
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus(
                "Failed to restart the container, please consult the logs"
            )
            return

        self.unit.status = ActiveStatus()


if __name__ == "__main__":  # pragma: nocover
    main.main(Oauth2ProxyK8sOperatorCharm)  # type: ignore
