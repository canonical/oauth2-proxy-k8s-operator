# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing


"""Charm unit tests."""

import json
import logging
from typing import Tuple
from unittest.mock import MagicMock, Mock

import pytest
import toml
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import CheckStatus
from ops.testing import Harness

from constants import WORKLOAD_CONTAINER, WORKLOAD_SERVICE

APP_NAME = "oauth2-proxy-k8s"
OAUTH_CLIENT_ID = "oauth2_proxy_client_id"
OAUTH_CLIENT_SECRET = "s3cR#T"
OAUTH_PROVIDER_INFO = {
    "authorization_endpoint": "https://example.oidc.com/oauth2/auth",
    "introspection_endpoint": "https://example.oidc.com/admin/oauth2/introspect",
    "issuer_url": "https://example.oidc.com",
    "jwks_endpoint": "https://example.oidc.com/.well-known/jwks.json",
    "scope": "openid profile email phone",
    "token_endpoint": "https://example.oidc.com/oauth2/token",
    "userinfo_endpoint": "https://example.oidc.com/userinfo",
}


def setup_peer_relation(harness: Harness) -> Tuple[int, str]:
    relation_id = harness.add_relation("oauth2-proxy", APP_NAME)
    return relation_id, APP_NAME


def setup_ingress_relation(harness: Harness) -> Tuple[int, str]:
    """Set up ingress relation."""
    harness.add_network("10.0.0.1")
    relation_id = harness.add_relation("ingress", "traefik")
    harness.add_relation_unit(relation_id, "traefik/0")
    url = f"http://ingress:80/{harness.model.name}-{APP_NAME}"
    harness.update_relation_data(
        relation_id,
        "traefik",
        {"ingress": json.dumps({"url": url})},
    )
    return relation_id, url


def setup_oauth_relation(harness: Harness) -> int:
    """Set up oauth relation."""
    relation_id = harness.add_relation("oauth", "hydra")
    harness.add_relation_unit(relation_id, "hydra/0")
    secret_id = harness.add_model_secret("hydra", {"secret": OAUTH_CLIENT_SECRET})
    harness.grant_secret(secret_id, APP_NAME)
    harness.update_relation_data(
        relation_id,
        "hydra",
        {
            "client_id": OAUTH_CLIENT_ID,
            "client_secret_id": secret_id,
            **OAUTH_PROVIDER_INFO,
        },
    )
    return relation_id


class TestPebbleReadyEvent:
    def test_pebble_container_can_connect(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, True)
        setup_peer_relation(harness)
        harness.charm.on.oauth2_proxy_pebble_ready.emit(WORKLOAD_CONTAINER)

        assert isinstance(harness.charm.unit.status, ActiveStatus)
        service = harness.model.unit.get_container(WORKLOAD_CONTAINER).get_service(WORKLOAD_SERVICE)
        assert service.is_running()

    def test_pebble_container_cannot_connect(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, False)
        harness.charm.on.oauth2_proxy_pebble_ready.emit(WORKLOAD_CONTAINER)

        assert harness.charm.unit.status == WaitingStatus("Waiting to connect to OAuth2-Proxy container")

    def test_on_pebble_ready_correct_plan(self, harness: Harness, mocked_cookie_encryption_key: MagicMock) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, True)
        setup_peer_relation(harness)
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        harness.charm.on.oauth2_proxy_pebble_ready.emit(container)

        expected_plan = {
            "services": {
                WORKLOAD_SERVICE: {
                    "summary": WORKLOAD_SERVICE,
                    "command": "/bin/oauth2-proxy --config /etc/config/oauth2-proxy/oauth2-proxy.cfg",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {
                        "OAUTH2_PROXY_COOKIE_SECRET": mocked_cookie_encryption_key,
                    },
                    "on-check-failure": {"up": "ignore"},
                }
            },
            "checks": {
                "up": {
                    "override": "replace",
                    "period": "10s",
                    "http": {"url": "http://localhost:4180/ready"},
                }
            },
        }
        updated_plan = harness.get_container_pebble_plan(WORKLOAD_CONTAINER).to_dict()
        assert expected_plan == updated_plan

    def test_oauth2_proxy_config_on_pebble_ready(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, True)
        setup_peer_relation(harness)
        harness.charm.on.oauth2_proxy_pebble_ready.emit(WORKLOAD_CONTAINER)
        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)

        container_config = container.pull(path="/etc/config/oauth2-proxy/oauth2-proxy.cfg", encoding="utf-8")

        config = toml.load(container_config)
        assert config["client_id"] == "default"
        assert config["client_secret"] == "default"
        assert config["email_domains"] == "*"
        assert config["set_xauthrequest"] == "true"


class TestConfigChangedEvent:
    def test_authenticated_emails_list_config_changed(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, True)
        setup_peer_relation(harness)
        harness.update_config({"authenticated-emails-list": "test@example.com,test1@example.com"})

        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        assert container.pull(path="/etc/config/oauth2-proxy/access_list.cfg", encoding="utf-8")

        container_config = container.pull(path="/etc/config/oauth2-proxy/oauth2-proxy.cfg", encoding="utf-8")
        config = toml.load(container_config)
        assert config["authenticated_emails_file"] == "/etc/config/oauth2-proxy/access_list.cfg"


class TestUpdateStatusEvent:
    def test_update_status_up(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, True)
        setup_peer_relation(harness)

        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        container.get_check = Mock(status="up")
        container.get_check.return_value.status = CheckStatus.UP
        harness.charm.on.update_status.emit()

        assert harness.model.unit.status == ActiveStatus()

    def test_update_status_down(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, True)
        setup_peer_relation(harness)
        harness.charm.on.oauth2_proxy_pebble_ready.emit(WORKLOAD_CONTAINER)

        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        container.get_check = Mock(status="up")
        container.get_check.return_value.status = CheckStatus.DOWN
        harness.charm.on.update_status.emit()

        assert harness.model.unit.status == MaintenanceStatus("Status check: DOWN")


class TestIngressIntegrationEvents:
    def test_ingress_relation_created(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, True)

        relation_id, url = setup_ingress_relation(harness)
        assert url == "http://ingress:80/testing-oauth2-proxy-k8s"

        app_data = harness.get_relation_data(relation_id, harness.charm.app)
        assert app_data == {
            "model": json.dumps(harness.model.name),
            "name": json.dumps("oauth2-proxy-k8s"),
            "port": json.dumps(4180),
            "strip-prefix": json.dumps(True),
        }

    def test_ingress_relation_revoked(self, harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO)
        harness.set_can_connect(WORKLOAD_CONTAINER, True)

        relation_id, _ = setup_ingress_relation(harness)
        caplog.clear()
        harness.remove_relation(relation_id)

        assert "This app no longer has ingress" in caplog.record_tuples[3]


class TestOAuthIntegrationEvents:
    def test_oauth_relation_requirer_data_sent(self, harness: Harness, mocked_cookie_encryption_key: MagicMock) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, True)
        relation_id = setup_oauth_relation(harness)

        app_data = harness.get_relation_data(relation_id, harness.charm.app)
        assert app_data == {
            "redirect_uri": "http://oauth2-proxy-k8s.testing.svc.cluster.local:4180/oauth2/callback",
            "scope": "openid email profile offline_access",
            "token_endpoint_auth_method": "client_secret_basic",
            "grant_types": '["authorization_code", "refresh_token"]',
            "audience": '[]'
        }

    def test_config_is_updated_with_oauth_relation_data(self, harness: Harness) -> None:
        harness.set_can_connect(WORKLOAD_CONTAINER, True)
        setup_peer_relation(harness)
        setup_oauth_relation(harness)
        harness.charm.on.oauth2_proxy_pebble_ready.emit(WORKLOAD_CONTAINER)

        container = harness.model.unit.get_container(WORKLOAD_CONTAINER)
        container_config = container.pull(path="/etc/config/oauth2-proxy/oauth2-proxy.cfg", encoding="utf-8")

        config = toml.load(container_config)
        assert config["client_id"] == OAUTH_CLIENT_ID
        assert config["client_secret"] == OAUTH_CLIENT_SECRET
        assert config["oidc_issuer_url"] == "https://example.oidc.com"
