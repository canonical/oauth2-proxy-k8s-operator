# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any, Generator, List

import pytest
from charms.oauth2_proxy_k8s.v0.auth_proxy import (
    AuthProxyConfigChangedEvent,
    AuthProxyConfigRemovedEvent,
    AuthProxyProvider,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: provider-tester
provides:
  auth-proxy:
    interface: auth_proxy
"""


class AuthProxyProviderCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.auth_proxy = AuthProxyProvider(self)
        self.events: List = []

        self.framework.observe(self.auth_proxy.on.proxy_config_changed, self._record_event)
        self.framework.observe(self.auth_proxy.on.config_removed, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(AuthProxyProviderCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin()
    yield harness
    harness.cleanup()


def setup_requirer_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("auth-proxy", "requirer")
    harness.add_relation_unit(relation_id, "requirer/0")
    harness.update_relation_data(
        relation_id,
        "requirer",
        {
            "protected_urls": '["https://example.com"]',
            "allowed_endpoints": '["welcome", "about/app"]',
            "headers": '["X-Auth-Request-User"]',
            "authenticated_emails": '["test@example.com"]',
            "authenticated_email_domains": '["canonical.com"]',
        },
    )

    return relation_id


class TestAuthProxyProviderIntegration:
    def test_auth_proxy_config_changed_event_emitted_when_relation_changed(
        self, harness: Harness
    ) -> None:
        _ = setup_requirer_relation(harness)

        assert any(isinstance(e, AuthProxyConfigChangedEvent) for e in harness.charm.events)

    def test_auth_proxy_config_changed_event_not_emitted_when_invalid_config_provided(
        self, harness: Harness
    ) -> None:
        relation_id = harness.add_relation("auth-proxy", "requirer")
        harness.add_relation_unit(relation_id, "requirer/0")
        harness.update_relation_data(
            relation_id,
            "requirer",
            {
                "protected_urls": "invalid-url",
                "allowed_endpoints": '["welcome", "about/app"]',
                "headers": '["X-User"]',
            },
        )

        assert not any(isinstance(e, AuthProxyConfigChangedEvent) for e in harness.charm.events)

    def test_auth_proxy_config_removed_event_emitted_when_relation_removed(
        self, harness: Harness
    ) -> None:
        relation_id = setup_requirer_relation(harness)
        harness.remove_relation(relation_id)

        assert any(isinstance(e, AuthProxyConfigRemovedEvent) for e in harness.charm.events)
