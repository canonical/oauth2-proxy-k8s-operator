# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from typing import Any

import ops.testing
import pytest
import yaml
from charms.oauth2_proxy_k8s.v0.forward_auth import (
    ForwardAuthConfig,
    ForwardAuthProvider,
    ForwardAuthProxySet,
    ForwardAuthRelationRemovedEvent,
    InvalidForwardAuthConfigEvent,
)
from conftest import FORWARD_AUTH_CONFIG, dict_to_relation_data
from ops.charm import CharmBase

METADATA = """
name: provider-tester
provides:
  forward-auth:
    interface: forward_auth
"""


class ForwardAuthProviderCharm(CharmBase):
    test_config = FORWARD_AUTH_CONFIG

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        forward_auth_config = ForwardAuthConfig(**self.test_config) if self.test_config else None
        self.forward_auth = ForwardAuthProvider(self, forward_auth_config=forward_auth_config)
        self.forward_auth.update_forward_auth_config(forward_auth_config)


class TestForwardAuthProviderIntegration:
    @pytest.fixture
    def context(self) -> ops.testing.Context:
        ForwardAuthProviderCharm.test_config = FORWARD_AUTH_CONFIG
        return ops.testing.Context(ForwardAuthProviderCharm, meta=yaml.safe_load(METADATA))

    def test_data_in_relation_bag(
        self,
        context: ops.testing.Context,
        forward_auth_relation: ops.testing.Relation,
    ) -> None:
        """Verifies that config is correctly written to the relation databag."""
        state_in = context.run(
            context.on.relation_created(forward_auth_relation),
            ops.testing.State(relations=[forward_auth_relation], leader=True)
        )

        rel_out = state_in.get_relation(forward_auth_relation.id)
        assert rel_out.local_app_data == dict_to_relation_data(FORWARD_AUTH_CONFIG)

    def test_missing_forward_auth_config_logged(
        self,
        context: ops.testing.Context,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verifies log message when config is missing."""
        caplog.set_level(logging.INFO)

        ForwardAuthProviderCharm.test_config = None

        context.run(context.on.start(), ops.testing.State(leader=True))

        assert "Forward-auth config is missing" in caplog.text

    def test_forward_auth_proxy_set_emitted_when_valid_config_provided(
        self,
        context: ops.testing.Context,
        forward_auth_relation: ops.testing.Relation,
    ) -> None:
        """Verifies success event emitted when remote app data matches configuration."""
        context.run(
            context.on.relation_changed(forward_auth_relation),
            ops.testing.State(relations=[forward_auth_relation], leader=True)
        )

        assert any(
            isinstance(e, ForwardAuthProxySet)
            for e in context.emitted_events
        )

    def test_forward_auth_invalid_config_emitted_when_app_not_related_to_ingress(
        self,
        context: ops.testing.Context,
        forward_auth_relation: ops.testing.Relation,
    ) -> None:
        """Verifies failure event when remote app data does not match configuration."""
        forward_auth_relation.remote_app_data["ingress_app_names"] = '["other-app"]'

        context.run(
            context.on.relation_changed(forward_auth_relation),
            ops.testing.State(relations=[forward_auth_relation], leader=True)
        )

        assert any(
            isinstance(e, InvalidForwardAuthConfigEvent)
            for e in context.emitted_events
        )

    def test_forward_auth_removed_emitted_when_relation_removed(
        self,
        context: ops.testing.Context,
        forward_auth_relation: ops.testing.Relation,
    ) -> None:
        """Verifies remove event."""
        state_in = ops.testing.State(relations=[forward_auth_relation], leader=True)
        context.run(context.on.relation_broken(forward_auth_relation), state_in)

        assert any(
            isinstance(e, ForwardAuthRelationRemovedEvent)
            for e in context.emitted_events
        )
