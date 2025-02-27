#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import logging

from charms.oauth2_proxy_k8s.v0.auth_proxy import AuthProxyConfig, AuthProxyRequirer
from charms.traefik_k8s.v2.ingress import IngressPerAppReadyEvent, IngressPerAppRequirer
from ops.charm import CharmBase, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus
from ops.pebble import Layer

AUTH_PROXY_ALLOWED_ENDPOINTS = ["anything/allowed"]
AUTH_PROXY_HEADERS = ["X-Auth-Request-User", "X-Auth-Request-Groups", "X-Auth-Request-Email"]
AUTH_PROXY_AUTHENTICATED_EMAILS = ["test@canonical.com", "test1@canonical.com"]
AUTH_PROXY_AUTHENTICATED_EMAIL_DOMAINS = ["example.com"]
HTTPBIN_PORT = 80

logger = logging.getLogger(__name__)


class AuthProxyRequirerMock(CharmBase):
    def __init__(self, framework):
        super().__init__(framework)
        self._container = self.unit.get_container("httpbin")
        self._service_name = "httpbin"

        self.ingress = IngressPerAppRequirer(
            self,
            host=f"{self.app.name}.{self.model.name}.svc.cluster.local",
            relation_name="ingress",
            port=HTTPBIN_PORT,
            strip_prefix=True,
        )

        self.auth_proxy_relation_name = "auth-proxy"
        self.auth_proxy = AuthProxyRequirer(
            self, self._auth_proxy_config, self.auth_proxy_relation_name
        )

        self.framework.observe(self.on.httpbin_pebble_ready, self._on_httpbin_pebble_ready)
        self.framework.observe(self.ingress.on.ready, self._on_ingress_ready)

    @property
    def _auth_proxy_config(self) -> AuthProxyConfig:
        return AuthProxyConfig(
            protected_urls=[
                self.ingress.url if self.ingress.url is not None else "https://some-test-url.com"
            ],
            headers=AUTH_PROXY_HEADERS,
            allowed_endpoints=AUTH_PROXY_ALLOWED_ENDPOINTS,
            authenticated_emails=AUTH_PROXY_AUTHENTICATED_EMAILS,
            authenticated_email_domains=AUTH_PROXY_AUTHENTICATED_EMAIL_DOMAINS
        )

    @property
    def _httpbin_pebble_layer(self) -> Layer:
        layer_config = {
            "summary": "auth-proxy-requirer-mock layer",
            "description": "pebble config layer for auth-proxy-requirer-mock",
            "services": {
                self._service_name: {
                    "override": "replace",
                    "summary": "httpbin layer",
                    "command": "gunicorn -b 0.0.0.0:80 httpbin:app -k gevent",
                    "startup": "enabled",
                }
            },
        }
        return Layer(layer_config)

    def _on_httpbin_pebble_ready(self, event: PebbleReadyEvent) -> None:
        self._container.add_layer("httpbin", self._httpbin_pebble_layer, combine=True)
        self._container.replan()
        self.unit.open_port(protocol="tcp", port=HTTPBIN_PORT)

        self.unit.status = ActiveStatus()

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info(f"This app's ingress URL: {event.url}")
        self.auth_proxy.update_auth_proxy_config(auth_proxy_config=self._auth_proxy_config)


if __name__ == "__main__":
    main(AuthProxyRequirerMock)
