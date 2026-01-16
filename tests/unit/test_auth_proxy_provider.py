# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any

import ops.testing
import pytest
import yaml
from charms.oauth2_proxy_k8s.v0.auth_proxy import (
    AuthProxyConfigChangedEvent,
    AuthProxyConfigRemovedEvent,
    AuthProxyProvider,
)
from ops.charm import CharmBase

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


class TestAuthProxyProviderIntegration:
    @pytest.fixture
    def context(self) -> ops.testing.Context:
        return ops.testing.Context(AuthProxyProviderCharm, meta=yaml.safe_load(METADATA))

    def test_auth_proxy_config_changed_event_emitted_when_relation_changed(
        self,
        context: ops.testing.Context,
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        """Verifies that AuthProxyConfigChangedEvent is emitted on valid relation changes."""
        context.run(
            context.on.relation_changed(auth_proxy_relation),
            ops.testing.State(leader=True, relations=[auth_proxy_relation])
        )

        assert any(
            isinstance(e, AuthProxyConfigChangedEvent)
            for e in context.emitted_events
        )

    def test_auth_proxy_config_changed_event_not_emitted_when_invalid_config_provided(
        self,
        context: ops.testing.Context,
    ) -> None:
        """Verifies that no success event is emitted if remote data is invalid."""
        relation = ops.testing.Relation(
            endpoint="auth-proxy",
            interface="auth_proxy",
            remote_app_name="requirer",
            remote_app_data={
                "allowed_endpoints": '["welcome", "about/app"]',
                "headers": '["X-User"]',
                "protected_urls": "invalid-url",
            }
        )

        context.run(
            context.on.relation_changed(relation),
            ops.testing.State(leader=True, relations=[relation])
        )

        assert not any(
            isinstance(e, AuthProxyConfigChangedEvent)
            for e in context.emitted_events
        )

    def test_auth_proxy_config_removed_event_emitted_when_relation_removed(
        self,
        context: ops.testing.Context,
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        """Verifies that AuthProxyConfigRemovedEvent is emitted on relation broken."""
        state_in = ops.testing.State(relations=[auth_proxy_relation], leader=True)
        context.run(context.on.relation_broken(auth_proxy_relation), state_in)

        assert any(
            isinstance(e, AuthProxyConfigRemovedEvent)
            for e in context.emitted_events
        )
