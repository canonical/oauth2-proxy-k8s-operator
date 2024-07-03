#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import logging

from charms.nginx_ingress_integrator.v0.nginx_route import require_nginx_route
from ops import main, pebble
from ops.charm import CharmBase
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import CheckStatus

from log import log_event_handler

logger = logging.getLogger(__name__)

HTTP_PORT = 80
OAUTH2_PROXY_VERSION = "v7.6.0"


class Oauth2ProxyK8SOperatorCharm(CharmBase):
    """Charm the application.

    Attrs:
        external_hostname: DNS listing used for external connections.
    """

    def __init__(self, *args):
        """Construct.

        Args:
            args: Ignore.
        """
        super().__init__(*args)

        self.name = "oauth2-proxy"
        self.framework.observe(self.on[self.name].pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.update_status, self._on_update_status)
        self.framework.observe(self.on.restart_action, self._on_restart)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        # Handle Ingress.
        self._require_nginx_route()

    @property
    def external_hostname(self):
        """Return the DNS listing used for external connections."""
        return self.config["external-hostname"] or self.app.name

    def _require_nginx_route(self):
        """Require nginx-route relation based on current configuration."""
        require_nginx_route(
            charm=self,
            service_hostname=self.external_hostname,
            service_name=self.app.name,
            service_port=HTTP_PORT,
            tls_secret_name=self.config["tls-secret-name"],
            backend_protocol="HTTP",
        )

    @log_event_handler(logger)
    def _on_pebble_ready(self, event):
        """Handle pebble ready event.

        Args:
            event: The event triggered when the relation changed.
        """
        self._update(event)

    @log_event_handler(logger)
    def _on_config_changed(self, event):
        """Handle configuration changes.

        Args:
            event: The event triggered when the relation changed.
        """
        self.unit.status = WaitingStatus("configuring application")
        self._update(event)

    @log_event_handler(logger)
    def _on_update_status(self, event):
        """Handle `update-status` events.

        Args:
            event: The `update-status` event triggered at intervals.
        """
        try:
            self._validate()
        except ValueError:
            return

        container = self.unit.get_container(self.name)
        valid_pebble_plan = self._validate_pebble_plan(container)
        if not valid_pebble_plan:
            self._update(event)
            return

        check = container.get_check("up")
        if check.status != CheckStatus.UP:
            self.unit.status = MaintenanceStatus("Status check: DOWN")
            return

        self.unit.set_workload_version(OAUTH2_PROXY_VERSION)
        self.unit.status = ActiveStatus()

    def _validate_pebble_plan(self, container):
        """Validate pebble plan.

        Args:
            container: application container

        Returns:
            bool of pebble plan validity
        """
        try:
            plan = container.get_plan().to_dict()
            return bool(plan["services"][self.name]["on-check-failure"])
        except (KeyError, pebble.ConnectionError):
            return False

    def _on_restart(self, event):
        """Restart application action handler.

        Args:
            event:The event triggered by the restart action
        """
        container = self.unit.get_container(self.name)
        if not container.can_connect():
            event.defer()
            return

        self.unit.status = MaintenanceStatus("restarting application")
        container.restart(self.name)

        event.set_results({"result": "application successfully restarted"})

    def _validate(self):
        """Validate that configuration and relations are valid and ready.

        Raises:
            ValueError: in case of invalid configuration.
        """
        if not self.config["upstream"]:
            raise ValueError("missing `upstream` config")

        if not self.config["cookie-secret"]:
            raise ValueError("missing `cookie-secret` config")

        if self.config["provider"] == "google" and (not self.config["client-id"] or not self.config["client-secret"]):
            raise ValueError("`client-id` and `client-secret` config must be set for `google` provider")

        if not self.config["authenticated-emails-list"] and "--email-domain=" not in self.config["additional-config"]:
            raise ValueError(
                "`--email-domain` must be set using `additional-config` if not setting `authenticated-emails-list`"
            )

    @log_event_handler(logger)
    def _update(self, event):
        """Update the application configuration and replan its execution.

        Args:
            event: The event triggered when the relation changed.
        """
        try:
            self._validate()
        except ValueError as err:
            self.unit.status = BlockedStatus(str(err))
            return

        container = self.unit.get_container(self.name)
        if not container.can_connect():
            event.defer()
            return

        command = f"/bin/oauth2-proxy --http-address=0.0.0.0:{HTTP_PORT}"
        for param in ["upstream", "provider", "client-id", "client-secret", "cookie-secret"]:
            if self.config[param]:
                command += f" --{param}={self.config[param]}"

        if self.config["authenticated-emails-list"]:
            users = "\n".join(self.config["authenticated-emails-list"].split(","))
            filename = "/etc/oauth2_proxy/access_list.cfg"
            container.push(filename, users, make_dirs=True)
            command += f" --authenticated-emails-file={filename}"

        if self.config["additional-config"]:
            command += f" {self.config['additional-config']}"

        self.model.unit.set_ports(HTTP_PORT)
        pebble_layer = {
            "summary": "oauth2 proxy layer",
            "services": {
                self.name: {
                    "summary": self.name,
                    "command": command,
                    "startup": "enabled",
                    "override": "replace",
                    "on-check-failure": {"up": "ignore"},
                }
            },
            "checks": {
                "up": {
                    "override": "replace",
                    "period": "10s",
                    "http": {"url": f"http://localhost:{HTTP_PORT}/ready"},
                }
            },
        }

        container.add_layer(self.name, pebble_layer, combine=True)
        container.replan()

        self.unit.status = MaintenanceStatus("replanning application")


if __name__ == "__main__":  # pragma: nocover
    main.main(Oauth2ProxyK8SOperatorCharm)  # type: ignore
