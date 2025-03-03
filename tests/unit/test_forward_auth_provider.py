# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from typing import Any, Dict, Generator, List

import pytest
from charms.oauth2_proxy_k8s.v0.forward_auth import (
    ForwardAuthConfig,
    ForwardAuthProvider,
    ForwardAuthProxySet,
    ForwardAuthRelationRemovedEvent,
    InvalidForwardAuthConfigEvent,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: provider-tester
provides:
  forward-auth:
    interface: forward_auth
"""
FORWARD_AUTH_CONFIG = {
    "decisions_address": "https://oauth2-proxy-k8s.testing.svc.cluster.local:4180",
    "app_names": ["charmed-app"],
    "headers": ["X-Auth-Request-User"],
}


class ForwardAuthProviderCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        forward_auth_config = ForwardAuthConfig(**FORWARD_AUTH_CONFIG)
        self.forward_auth = ForwardAuthProvider(self, forward_auth_config=forward_auth_config)
        self.events: List = []

        self.framework.observe(self.forward_auth.on.forward_auth_proxy_set, self._record_event)
        self.framework.observe(
            self.forward_auth.on.invalid_forward_auth_config, self._record_event
        )
        self.framework.observe(
            self.forward_auth.on.forward_auth_relation_removed, self._record_event
        )

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(ForwardAuthProviderCharm, meta=METADATA)
    harness.set_model_name("testing")
    harness.set_leader(True)
    harness.begin_with_initial_hooks()
    yield harness
    harness.cleanup()


def setup_requirer_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("forward-auth", "requirer")
    harness.add_relation_unit(relation_id, "requirer/0")
    harness.update_relation_data(
        relation_id,
        "requirer",
        {"ingress_app_names": '["charmed-app"]'},
    )

    return relation_id


def dict_to_relation_data(dic: Dict) -> Dict:
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


class TestForwardAuthProviderIntegration:
    def test_data_in_relation_bag(self, harness: Harness) -> None:
        relation_id = harness.add_relation("forward-auth", "requirer")
        relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

        assert relation_data == dict_to_relation_data(FORWARD_AUTH_CONFIG)

    def test_missing_forward_auth_config_logged(
        self, harness: Harness, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)

        harness.charm.forward_auth.update_forward_auth_config(forward_auth_config="")
        assert "Forward-auth config is missing" in caplog.text

    def test_forward_auth_proxy_set_emitted_when_valid_config_provided(self, harness: Harness) -> None:
        _ = setup_requirer_relation(harness)

        assert any(isinstance(e, ForwardAuthProxySet) for e in harness.charm.events)

    def test_forward_auth_invalid_config_emitted_when_app_not_related_to_ingress(
        self, harness: Harness,
    ) -> None:
        relation_id = harness.add_relation("forward-auth", "requirer")
        harness.add_relation_unit(relation_id, "requirer/0")
        harness.update_relation_data(
            relation_id,
            "requirer",
            {"ingress_app_names": '["other-app"]'},
        )

        assert any(isinstance(e, InvalidForwardAuthConfigEvent) for e in harness.charm.events)

    def test_forward_auth_removed_emitted_when_relation_removed(self, harness: Harness) -> None:
        relation_id = setup_requirer_relation(harness)
        harness.remove_relation(relation_id)

        assert any(isinstance(e, ForwardAuthRelationRemovedEvent) for e in harness.charm.events)
