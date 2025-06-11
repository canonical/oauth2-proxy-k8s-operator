# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from typing import Any, Dict, Generator, List

import pytest
from charms.oauth2_proxy_k8s.v0.auth_proxy import (
    AuthProxyConfig,
    AuthProxyConfigError,
    AuthProxyRelationRemovedEvent,
    AuthProxyRequirer,
    InvalidAuthProxyConfigEvent,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: requirer-tester
requires:
  auth-proxy:
    interface: auth_proxy
"""

AUTH_PROXY_CONFIG = {
    "protected_urls": ["https://example.com"],
    "allowed_endpoints": ["welcome", "about/app"],
    "headers": ["X-Auth-Request-User"],
    "authenticated_emails": ["test@example.com"],
    "authenticated_email_domains": ["canonical.com"],
}


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(AuthProxyRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


def dict_to_relation_data(dic: Dict) -> Dict:
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


class AuthProxyRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        auth_proxy_config = AuthProxyConfig(**AUTH_PROXY_CONFIG)
        self.auth_proxy = AuthProxyRequirer(self, auth_proxy_config=auth_proxy_config)

        self.events: List = []
        self.framework.observe(self.auth_proxy.on.invalid_auth_proxy_config, self._record_event)
        self.framework.observe(self.auth_proxy.on.auth_proxy_relation_removed, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


class TestAuthProxyRequirerIntegration:
    def test_data_in_relation_bag(self, harness: Harness) -> None:
        relation_id = harness.add_relation("auth-proxy", "provider")
        relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

        expected_data = dict_to_relation_data(AUTH_PROXY_CONFIG)

        assert relation_data["app_name"] == "requirer-tester"
        assert relation_data["allowed_endpoints"] == expected_data["allowed_endpoints"]
        assert relation_data["headers"] == expected_data["headers"]
        assert relation_data["authenticated_emails"] == expected_data["authenticated_emails"]
        assert relation_data["authenticated_email_domains"] == expected_data["authenticated_email_domains"]

    def test_warning_when_http_protected_url_provided(
        self, harness: Harness, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Check that a warning appears when one of the provided urls uses http scheme."""
        caplog.set_level(logging.WARNING)
        auth_proxy_config = AuthProxyConfig(**AUTH_PROXY_CONFIG)
        auth_proxy_config.protected_urls = ["https://some-url.com", "http://some-other-url.com"]

        harness.charm.auth_proxy.update_auth_proxy_config(auth_proxy_config=auth_proxy_config)
        assert (
            f"Provided URL {auth_proxy_config.protected_urls[1]} uses http scheme. Don't do this in production"
            in caplog.text
        )

    def test_exception_raised_when_invalid_protected_url(self, harness: Harness) -> None:
        auth_proxy_config = AuthProxyConfig(**AUTH_PROXY_CONFIG)
        auth_proxy_config.protected_urls = ["https://some-valid-url.com", "invalid-url"]

        with pytest.raises(
            AuthProxyConfigError, match=f"Invalid URL {auth_proxy_config.protected_urls[1]}"
        ):
            harness.charm.auth_proxy.update_auth_proxy_config(auth_proxy_config=auth_proxy_config)

    def test_exception_raised_when_invalid_header(self, harness: Harness) -> None:
        auth_proxy_config = AuthProxyConfig(**AUTH_PROXY_CONFIG)
        auth_proxy_config.headers = ["X-Auth-Request-User", "X-Invalid-Header"]

        with pytest.raises(AuthProxyConfigError, match="Unsupported header"):
            harness.charm.auth_proxy.update_auth_proxy_config(auth_proxy_config=auth_proxy_config)

    def test_auth_proxy_relation_removed_event_emitted(self, harness: Harness) -> None:
        relation_id = harness.add_relation("auth-proxy", "provider")
        harness.add_relation_unit(relation_id, "provider/0")

        harness.remove_relation(relation_id)

        assert any(isinstance(e, AuthProxyRelationRemovedEvent) for e in harness.charm.events)


class InvalidConfigAuthProxyRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        auth_proxy_config = AuthProxyConfig(**AUTH_PROXY_CONFIG)
        auth_proxy_config.headers = ["X-Invalid-Header"]
        self.auth_proxy = AuthProxyRequirer(self, auth_proxy_config=auth_proxy_config)

        self.events: List = []
        self.framework.observe(self.auth_proxy.on.invalid_auth_proxy_config, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def harness_invalid_config() -> Generator:
    harness = Harness(InvalidConfigAuthProxyRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


class TestAuthProxyRequirerIntegrationInvalidConfig:
    def test_event_emitted_when_invalid_auth_proxy_config(
        self, harness_invalid_config: Harness
    ) -> None:
        harness_invalid_config.add_relation("auth-proxy", "provider")

        assert any(
            isinstance(e, InvalidAuthProxyConfigEvent) for e in harness_invalid_config.charm.events
        )
