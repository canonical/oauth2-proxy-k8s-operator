# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from typing import Any

import ops.testing
import pytest
import yaml
from charms.oauth2_proxy_k8s.v0.auth_proxy import (
    AuthProxyConfig,
    AuthProxyRelationRemovedEvent,
    AuthProxyRequirer,
)
from conftest import AUTH_PROXY_CONFIG
from ops.charm import CharmBase

METADATA = """
name: requirer-tester
requires:
  auth-proxy:
    interface: auth_proxy
"""


class AuthProxyRequirerCharm(CharmBase):
    test_config = AUTH_PROXY_CONFIG

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        self.auth_proxy_config = AuthProxyConfig(**self.test_config) if self.test_config else None
        self.auth_proxy = AuthProxyRequirer(self, auth_proxy_config=self.auth_proxy_config)
        self.auth_proxy.update_auth_proxy_config(self.auth_proxy_config)


class TestAuthProxyRequirerIntegration:
    @pytest.fixture
    def context(self) -> ops.testing.Context:
        AuthProxyRequirerCharm.test_config = AUTH_PROXY_CONFIG
        return ops.testing.Context(AuthProxyRequirerCharm, meta=yaml.safe_load(METADATA))

    def test_data_in_relation_bag(
        self,
        context: ops.testing.Context,
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        state_in = context.run(
            context.on.relation_created(auth_proxy_relation),
            ops.testing.State(relations=[auth_proxy_relation], leader=True)
        )

        rel_out = state_in.get_relation(auth_proxy_relation.id)
        rel_data = rel_out.local_app_data

        assert json.loads(rel_data["allowed_endpoints"]) == AUTH_PROXY_CONFIG["allowed_endpoints"]
        assert json.loads(rel_data["headers"]) == AUTH_PROXY_CONFIG["headers"]

    def test_warning_when_http_protected_url_provided(
        self,
        context: ops.testing.Context,
        auth_proxy_relation: ops.testing.Relation,
        caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)

        new_urls_config = ["https://some-url.com", "http://some-other-url.com"]
        AuthProxyRequirerCharm.test_config = {**AUTH_PROXY_CONFIG, "protected_urls": new_urls_config}

        context.run(
            context.on.relation_created(auth_proxy_relation),
            ops.testing.State(leader=True, relations=[auth_proxy_relation])
        )

        assert (
            f"Provided URL {new_urls_config[1]} uses http scheme. Don't do this in production"
            in caplog.text
        )

    def test_exception_raised_when_invalid_header(
        self,
        context: ops.testing.Context,
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        """Verifies that an exception is raised when invalid headers config is provided."""
        invalid_headers = ["X-Auth-Request-User", "X-Invalid-Header"]
        AuthProxyRequirerCharm.test_config = {**AUTH_PROXY_CONFIG, "headers": invalid_headers}

        with pytest.raises(ops.testing.errors.UncaughtCharmError) as excinfo:
            context.run(
                context.on.start(),
                ops.testing.State(leader=True, relations=[auth_proxy_relation])
            )

        assert "Unsupported header" in str(excinfo.value)

    def test_auth_proxy_relation_removed_event_emitted(
        self,
        context: ops.testing.Context,
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        """Verifies that AuthProxyRelationRemovedEvent is emitted on relation broken."""
        context.run(
            context.on.relation_broken(auth_proxy_relation),
            ops.testing.State(relations=[auth_proxy_relation], leader=True)
        )

        assert any(
            isinstance(e, AuthProxyRelationRemovedEvent)
            for e in context.emitted_events
        )
