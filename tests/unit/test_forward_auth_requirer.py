# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Any, Dict, Generator, List

import pytest
from charms.oauth2_proxy_k8s.v0.forward_auth import (
    AuthConfigChangedEvent,
    AuthConfigRemovedEvent,
    ForwardAuthRequirer,
    ForwardAuthRequirerConfig,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: requirer-tester
requires:
  forward-auth:
    interface: forward_auth
    limit: 1
"""

FORWARD_AUTH_REQUIRER_CONFIG = {
    "ingress_app_names": ["charmed-app"],
}


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(ForwardAuthRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


@pytest.fixture()
def provider_info() -> Dict:
    return {
        "decisions_address": "https://oauth2-proxy-k8s.testing.svc.cluster.local:4180",
        "app_names": ["charmed-app"],
        "headers": ["X-User"],
    }


def dict_to_relation_data(dic: Dict) -> Dict:
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


class ForwardAuthRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.forward_auth = ForwardAuthRequirer(self)

        self.events: List = []
        self.framework.observe(self.forward_auth.on.auth_config_changed, self._record_event)
        self.framework.observe(self.forward_auth.on.auth_config_removed, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


def setup_provider_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("forward-auth", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        {
            "decisions_address": "https://oauth2-proxy-k8s.testing.svc.cluster.local:4180",
            "app_names": '["charmed-app"]',
            "headers": '["X-User"]',
        },
    )

    return relation_id


class TestForwardAuthRequirerIntegration:
    def test_data_in_relation_bag(self, harness: Harness) -> None:
        relation_id = harness.add_relation("forward-auth", "provider")
        relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

        # Call update_requirer_relation_data() to mimic traefik behaviour
        forward_auth_requirer_config = ForwardAuthRequirerConfig(**FORWARD_AUTH_REQUIRER_CONFIG)
        harness.charm.forward_auth.update_requirer_relation_data(forward_auth_requirer_config)

        assert relation_data == dict_to_relation_data(FORWARD_AUTH_REQUIRER_CONFIG)

    def test_get_provider_info_when_data_available(
        self, harness: Harness, provider_info: Dict
    ) -> None:
        _ = setup_provider_relation(harness)

        expected_provider_info = harness.charm.forward_auth.get_provider_info()

        assert expected_provider_info.decisions_address == provider_info["decisions_address"]
        assert expected_provider_info.app_names == provider_info["app_names"]
        assert expected_provider_info.headers == provider_info["headers"]

    def test_forward_auth_config_changed_emitted_when_relation_changed(
        self, harness: Harness
    ) -> None:
        _ = setup_provider_relation(harness)

        assert any(isinstance(e, AuthConfigChangedEvent) for e in harness.charm.events)

    def test_forward_auth_removed_emitted_when_relation_removed(self, harness: Harness) -> None:
        relation_id = setup_provider_relation(harness)
        harness.remove_relation(relation_id)

        assert any(isinstance(e, AuthConfigRemovedEvent) for e in harness.charm.events)
