# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any

import ops.testing
import pytest
import yaml
from charms.oauth2_proxy_k8s.v0.forward_auth import (
    AuthConfigChangedEvent,
    AuthConfigRemovedEvent,
    ForwardAuthRequirer,
    ForwardAuthRequirerConfig,
)
from conftest import (
    FORWARD_AUTH_CONFIG,
    FORWARD_AUTH_REQUIRER_CONFIG,
    dict_to_relation_data,
)
from ops.charm import CharmBase

METADATA = """
name: requirer-tester
requires:
  forward-auth:
    interface: forward_auth
    limit: 1
"""


class ForwardAuthRequirerCharm(CharmBase):
    test_config = FORWARD_AUTH_REQUIRER_CONFIG

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        forward_auth_config = ForwardAuthRequirerConfig(**self.test_config) if self.test_config else None
        self.forward_auth = ForwardAuthRequirer(self)
        self.forward_auth.update_requirer_relation_data(forward_auth_config)


class TestForwardAuthRequirerIntegration:
    @pytest.fixture
    def context(self) -> ops.testing.Context:
        ForwardAuthRequirerCharm.test_config = FORWARD_AUTH_REQUIRER_CONFIG
        return ops.testing.Context(ForwardAuthRequirerCharm, meta=yaml.safe_load(METADATA))

    @pytest.fixture
    def forward_auth_relation_requirer(self) -> ops.testing.Relation:
        return ops.testing.Relation(
            endpoint="forward-auth",
            interface="forward_auth",
            remote_app_data=dict_to_relation_data(FORWARD_AUTH_CONFIG),
            local_app_data=dict_to_relation_data(FORWARD_AUTH_REQUIRER_CONFIG),
        )

    def test_data_in_relation_bag(
        self,
        context: ops.testing.Context,
        forward_auth_relation_requirer: ops.testing.Relation,
    ) -> None:
        """Verifies that config is correctly written to the relation databag."""
        state_in = context.run(
            context.on.relation_created(forward_auth_relation_requirer),
            ops.testing.State(relations=[forward_auth_relation_requirer], leader=True)
        )

        rel_out = state_in.get_relation(forward_auth_relation_requirer.id)
        assert rel_out.local_app_data == dict_to_relation_data(FORWARD_AUTH_REQUIRER_CONFIG)

    def test_get_provider_info_when_data_available(
        self,
        context: ops.testing.Context,
        forward_auth_relation_requirer: ops.testing.Relation,
    ) -> None:
        """Verifies that provider info can be retrieved successfully from relation data."""
        with context(
            context.on.relation_changed(forward_auth_relation_requirer),
            ops.testing.State(relations=[forward_auth_relation_requirer], leader=True)
        ) as manager:
            manager.run()

            expected_provider_info = manager.charm.forward_auth.get_provider_info()
            assert expected_provider_info.decisions_address == FORWARD_AUTH_CONFIG["decisions_address"]
            assert expected_provider_info.app_names == FORWARD_AUTH_CONFIG["app_names"]
            assert expected_provider_info.headers == FORWARD_AUTH_CONFIG["headers"]

    def test_forward_auth_config_changed_emitted_when_relation_changed(
        self,
        context: ops.testing.Context,
        forward_auth_relation_requirer: ops.testing.Relation,
    ) -> None:
        """Verifies that AuthConfigChangedEvent is emitted when the relation changes."""
        context.run(
            context.on.relation_changed(forward_auth_relation_requirer),
            ops.testing.State(relations=[forward_auth_relation_requirer], leader=True)
        )

        assert any(
            isinstance(e, AuthConfigChangedEvent)
            for e in context.emitted_events
        )

    def test_forward_auth_removed_emitted_when_relation_removed(
        self,
        context: ops.testing.Context,
        forward_auth_relation_requirer: ops.testing.Relation,
    ) -> None:
        """Verifies that AuthConfigRemovedEvent is emitted when the relation is broken."""
        state_in = ops.testing.State(relations=[forward_auth_relation_requirer], leader=True)
        context.run(context.on.relation_broken(forward_auth_relation_requirer), state_in)
        assert any(
            isinstance(e, AuthConfigRemovedEvent)
            for e in context.emitted_events
        )
