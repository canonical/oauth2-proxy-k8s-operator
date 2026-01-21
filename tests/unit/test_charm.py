# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing


"""Charm unit tests."""

import logging
from dataclasses import replace
from unittest.mock import MagicMock

import ops.testing
import pytest
from conftest import (
    COOKIE_SECRET,
    OAUTH_CLIENT_ID,
    OAUTH_CLIENT_SECRET,
    OAUTH_PROVIDER_INFO,
    create_state,
)
from ops import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import CheckLevel, CheckStartup, CheckStatus
from pytest_mock import MockerFixture

from constants import (
    OAUTH2_PROXY_API_PORT,
    PEBBLE_READY_CHECK_NAME,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from integrations import TrustedCertificatesTransferIntegration


class TestPebbleReadyEvent:
    def test_pebble_ready_can_connect(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
    ) -> None:
        state_in = create_state(relations=[peer_relation])

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = context.run(context.on.pebble_ready(container), state_in)

        assert state_out.unit_status == ActiveStatus()

    def test_pebble_ready_cannot_connect(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
    ) -> None:
        state_in = create_state(can_connect=False, relations=[peer_relation])

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = context.run(context.on.pebble_ready(container), state_in)

        assert state_out.unit_status == WaitingStatus("Waiting to connect to OAuth2-Proxy container")

    def test_on_pebble_ready_correct_plan(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
    ) -> None:
        state_in = create_state(relations=[peer_relation])

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = context.run(context.on.pebble_ready(container), state_in)
        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container_out.layers[WORKLOAD_CONTAINER]

        expected_plan = {
            "services": {
                WORKLOAD_SERVICE: {
                    "summary": WORKLOAD_SERVICE,
                    "command": "/bin/oauth2-proxy",
                    "startup": "enabled",
                    "override": "replace",
                    "environment": {
                        "HTTPS_PROXY": None,
                        "HTTP_PROXY": None,
                        "NO_PROXY": None,
                        "OAUTH2_PROXY_CLIENT_ID": "default",
                        "OAUTH2_PROXY_CLIENT_SECRET": "default",
                        "OAUTH2_PROXY_COOKIE_SECRET": COOKIE_SECRET,
                        "OAUTH2_PROXY_EMAIL_DOMAINS": "*",
                        "OAUTH2_PROXY_HTTP_ADDRESS": f"0.0.0.0:{OAUTH2_PROXY_API_PORT}",
                        "OAUTH2_PROXY_REDIRECT_URL": "http://oauth2-proxy-k8s.testing.svc.cluster.local:4180/oauth2/callback",
                        "OAUTH2_PROXY_REVERSE_PROXY": "true",
                        "OAUTH2_PROXY_SET_XAUTHREQUEST": "true",
                        "OAUTH2_PROXY_SSL_INSECURE_SKIP_VERIFY": "false",
                        "OAUTH2_PROXY_UPSTREAMS": "static://200",
                        "OAUTH2_PROXY_WHITELIST_DOMAINS": "oauth2-proxy-k8s.testing.svc.cluster.local",
                    },
                    "on-check-failure": {"ready": "ignore"},
                }
            },
            "summary": "oauth2 proxy layer",
            "description": "pebble config layer for oauth2-proxy-k8s-operator",
            "checks": {
                PEBBLE_READY_CHECK_NAME: {
                    "override": "replace",
                    "period": "10s",
                    "http": {"url": "http://localhost:4180/ready"},
                }
            },
        }

        assert expected_plan == layer.to_dict()

    def test_workload_version_set(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
    ) -> None:
        state_in = create_state(relations=[peer_relation])

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = context.run(context.on.pebble_ready(container), state_in)

        assert state_out.workload_version == "v7.8.1"


class TestConfigChangedEvent:
    def test_oauth2_proxy_config_with_dev_flag(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
    ) -> None:
        state_in = create_state(config={"dev": True}, relations=[peer_relation])
        container = state_in.get_container(WORKLOAD_CONTAINER)

        state_out = context.run(context.on.pebble_ready(container), state_in)
        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container_out.layers[WORKLOAD_CONTAINER]
        env = layer.services[WORKLOAD_CONTAINER].environment

        assert env["OAUTH2_PROXY_SSL_INSECURE_SKIP_VERIFY"] == "true"


class TestAuthProxyEvents:
    def test_config_file_when_auth_proxy_config_provided(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        state_in = create_state(relations=[peer_relation, auth_proxy_relation])
        container = state_in.get_container(WORKLOAD_CONTAINER)

        state_out = context.run(context.on.pebble_ready(container), state_in)
        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container_out.layers[WORKLOAD_CONTAINER]
        env = layer.services[WORKLOAD_CONTAINER].environment
        assert (
            env["OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE"]
            == "/etc/config/oauth2-proxy/access_list.cfg"
        )
        assert env["OAUTH2_PROXY_EMAIL_DOMAINS"] == "example.com"
        assert sorted(env["OAUTH2_PROXY_SKIP_AUTH_ROUTES"].split(",")) == ["about/app", "welcome"]
        assert env["OAUTH2_PROXY_SET_XAUTHREQUEST"] == "true"

    def test_authenticated_emails_file_created_when_auth_proxy_config_provided(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        auth_proxy_relation: ops.testing.Relation,
    ) -> None:
        state_in = create_state(relations=[peer_relation, auth_proxy_relation])
        container = state_in.get_container(WORKLOAD_CONTAINER)

        state_out = context.run(context.on.pebble_ready(container), state_in)
        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        filesystem_root = container_out.get_filesystem(context)

        file_path = filesystem_root / "etc/config/oauth2-proxy/access_list.cfg"

        assert file_path.exists()
        assert "test@canonical.com" in file_path.read_text()

    def test_forward_auth_updated_when_auth_proxy_set(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        auth_proxy_relation: ops.testing.Relation,
        mocked_forward_auth_update: MagicMock,
        mocked_oauth2_proxy_is_running: MagicMock,
    ) -> None:
        state_in = create_state(relations=[peer_relation, auth_proxy_relation])

        context.run(context.on.relation_changed(auth_proxy_relation), state_in)

        mocked_forward_auth_update.assert_called()

    def test_auth_proxy_relation_departed(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        auth_proxy_relation: ops.testing.Relation,
        mocked_forward_auth_update: MagicMock,
        mocked_oauth2_proxy_is_running: MagicMock,
    ) -> None:
        state_in = create_state(relations=[peer_relation, auth_proxy_relation])
        context.run(context.on.relation_broken(auth_proxy_relation), state_in)

        mocked_forward_auth_update.assert_called()

    def test_auth_proxy_with_missing_optional_fields(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
    ) -> None:
        """Test that charm handles missing optional fields gracefully."""
        # Create a relation with required data but missing optional fields
        minimal_auth_proxy_relation = ops.testing.Relation(
            endpoint="auth-proxy",
            interface="auth_proxy",
            remote_app_name="requirer",
            remote_app_data={
                "protected_urls": '["https://example.com"]',
                "allowed_endpoints": '[]',
                "headers": '["X-Auth-Request-User"]',
                # authenticated_emails is intentionally missing
                # authenticated_email_domains is intentionally missing
            },
        )
        state_in = create_state(relations=[peer_relation, minimal_auth_proxy_relation])
        container = state_in.get_container(WORKLOAD_CONTAINER)

        # This should not raise KeyError even when optional fields are missing
        state_out = context.run(context.on.pebble_ready(container), state_in)

        # Verify the charm is in active status (not crashed with KeyError)
        assert state_out.unit_status == ActiveStatus()

        # Verify the environment is set up correctly with defaults
        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container_out.layers[WORKLOAD_CONTAINER]
        env = layer.services[WORKLOAD_CONTAINER].environment

        # authenticated_emails file should not be set since the field was missing
        assert "OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE" not in env
        # Default OAUTH2_PROXY_EMAIL_DOMAINS = "*" is always present
        assert env["OAUTH2_PROXY_EMAIL_DOMAINS"] == "*"


class TestForwardAuthEvents:
    def test_forward_auth_set(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        forward_auth_relation: ops.testing.Relation,
    ) -> None:
        state_in = create_state(relations=[peer_relation, forward_auth_relation])

        state_out = context.run(context.on.relation_changed(forward_auth_relation), state_in)
        rel_out = state_out.get_relation(forward_auth_relation.id)

        assert rel_out.local_app_data == {
            "app_names": '["charmed-app"]',
            "decisions_address": f"https://oauth2-proxy-k8s.{state_out.model.name}.svc.cluster.local:4180",
            "headers": '["X-Auth-Request-User"]',
        }

        assert state_out.unit_status == ActiveStatus("OAuth2 Proxy is configured")

    def test_forward_auth_integration_removed(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        forward_auth_relation: ops.testing.Relation,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.INFO)
        state_in = create_state(relations=[peer_relation, forward_auth_relation])
        state_out = context.run(context.on.relation_broken(forward_auth_relation), state_in)

        assert "The proxy was unset" in caplog.text
        assert state_out.unit_status == ActiveStatus()


class TestUpdateStatusEvent:
    def test_update_status_up_active(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        expected_pebble_layer: ops.pebble.Layer,
    ) -> None:
        container = ops.testing.Container(
            name=WORKLOAD_CONTAINER,
            can_connect=True,
            layers={"oauth2-proxy": expected_pebble_layer},
            check_infos={
                ops.testing.CheckInfo(
                    name=PEBBLE_READY_CHECK_NAME,
                    status=ops.pebble.CheckStatus.UP,
                    level=CheckLevel.UNSET,
                    startup=CheckStartup.UNSET,
                    threshold=None,
                )
            }
        )

        state_in = create_state(relations=[peer_relation], container=container)
        # Simulate ActiveStatus before running update event
        state_in = replace(state_in, unit_status=ActiveStatus())

        state_out = context.run(context.on.update_status(), state_in)

        assert state_out.unit_status == ActiveStatus()

    def test_update_status_respects_blocked_status(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        expected_pebble_layer: ops.pebble.Layer,
    ) -> None:
        container = ops.testing.Container(
            name=WORKLOAD_CONTAINER,
            can_connect=True,
            layers={"oauth2-proxy": expected_pebble_layer},
            check_infos={
                ops.testing.CheckInfo(
                    name=PEBBLE_READY_CHECK_NAME,
                    status=CheckStatus.UP,
                    level=CheckLevel.UNSET,
                    startup=CheckStartup.UNSET,
                    threshold=None,
                )
            }
        )

        state_in = create_state(
            relations=[peer_relation],
            container=container
        )

        # Verify that update-status does not overwrite BlockedStatus even if checks pass
        initial_status = BlockedStatus()
        state_in = replace(state_in, unit_status=initial_status)

        state_out = context.run(context.on.update_status(), state_in)

        assert state_out.unit_status == initial_status

    def test_update_status_down(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        expected_pebble_layer: ops.pebble.Layer,
    ) -> None:
        container = ops.testing.Container(
            name=WORKLOAD_CONTAINER,
            can_connect=True,
            layers={"oauth2-proxy": expected_pebble_layer},
            check_infos={
                ops.testing.CheckInfo(
                    name=PEBBLE_READY_CHECK_NAME,
                    status=CheckStatus.DOWN,
                    level=CheckLevel.UNSET,
                    startup=CheckStartup.UNSET,
                    threshold=None,
                )
            }
        )

        state_in = create_state(relations=[peer_relation], container=container)
        state_out = context.run(context.on.update_status(), state_in)

        assert state_out.unit_status == MaintenanceStatus("Status check: DOWN")


class TestIngressIntegrationEvents:
    def test_ingress_relation_created(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        ingress_relation: ops.testing.Relation,
    ) -> None:
        state_in = create_state(relations=[peer_relation, ingress_relation])
        container = state_in.get_container(WORKLOAD_CONTAINER)

        state_out = context.run(context.on.pebble_ready(container), state_in)
        rel_out = state_out.get_relation(ingress_relation.id)

        assert rel_out.remote_app_data["url"] == "http://ingress:80/testing-oauth2-proxy-k8s"
        assert rel_out.local_app_data == {}

    def test_ingress_relation_revoked(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        ingress_relation: ops.testing.Relation,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.INFO)
        state_in = create_state(relations=[peer_relation, ingress_relation])
        state_out = context.run(context.on.relation_broken(ingress_relation), state_in)

        assert "This app no longer has ingress" in caplog.text
        assert state_out.unit_status == ActiveStatus()


class TestOAuthIntegrationEvents:
    def test_oauth_relation_requirer_data_sent(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        oauth_relation: ops.testing.Relation,
        oauth_secret: ops.testing.Secret,
    ) -> None:
        state_in = create_state(relations=[peer_relation, oauth_relation], secrets=[oauth_secret])

        state_out = context.run(context.on.relation_changed(oauth_relation), state_in)
        rel_out = state_out.get_relation(oauth_relation.id)

        assert rel_out.local_app_data == {
            "redirect_uri": "http://oauth2-proxy-k8s.testing.svc.cluster.local:4180/oauth2/callback",
            "scope": "openid email profile offline_access",
            "token_endpoint_auth_method": "client_secret_basic",
            "grant_types": '["authorization_code", "refresh_token"]',
            "audience": "[]",
        }

    def test_config_is_updated_with_oauth_relation_data(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        oauth_relation: ops.testing.Relation,
        oauth_secret: ops.testing.Secret,
    ) -> None:
        state_in = create_state(relations=[peer_relation, oauth_relation], secrets=[oauth_secret])

        state_out = context.run(context.on.relation_changed(oauth_relation), state_in)
        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container_out.layers[WORKLOAD_CONTAINER]
        env = layer.services[WORKLOAD_CONTAINER].environment

        assert env["OAUTH2_PROXY_CLIENT_ID"] == OAUTH_CLIENT_ID
        assert env["OAUTH2_PROXY_CLIENT_SECRET"] == OAUTH_CLIENT_SECRET
        assert env["OAUTH2_PROXY_OIDC_ISSUER_URL"] == "https://example.oidc.com"


class TestTrustedCertificatesTransferIntegration:
    def test_warning_when_no_certs_transfer_integration(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.WARNING)
        state_in = create_state(relations=[peer_relation])

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = context.run(context.on.pebble_ready(container), state_in)

        assert "Missing certificate_transfer integration" in caplog.text
        assert state_out.unit_status == ActiveStatus()

    def test_trusted_certs_update_called(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        certificates_relation: ops.testing.Relation,
        mocker: MockerFixture,
    ) -> None:
        mocked_update = mocker.patch.object(
            TrustedCertificatesTransferIntegration,
            "update_trusted_ca_certs",
            return_value=None
        )

        state_in = create_state(relations=[peer_relation, certificates_relation])

        container = state_in.get_container(WORKLOAD_CONTAINER)
        context.run(context.on.pebble_ready(container), state_in)

        mocked_update.assert_called_once()


class TestEnableExtraJWTBearerTokens:
    def test_enable_extra_jwt_bearer_tokens(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        oauth_relation: ops.testing.Relation,
        oauth_secret: ops.testing.Secret,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        state_in = create_state(
            relations=[peer_relation, oauth_relation],
            secrets=[oauth_secret],
            config={"enable_jwt_bearer_tokens": True}
        )

        container = state_in.get_container(WORKLOAD_CONTAINER)
        state_out = context.run(context.on.pebble_ready(container), state_in)

        container_out = state_out.get_container(WORKLOAD_CONTAINER)
        layer = container_out.layers[WORKLOAD_CONTAINER]
        env = layer.services[WORKLOAD_CONTAINER].environment

        assert env["OAUTH2_PROXY_SKIP_JWT_BEARER_TOKENS"] == "true"
        assert env["OAUTH2_PROXY_EXTRA_JWT_ISSUERS"] == (
            f"{OAUTH_PROVIDER_INFO['issuer_url']}={OAUTH_CLIENT_ID}"
        )
        assert env["OAUTH2_PROXY_BEARER_TOKEN_LOGIN_FALLBACK"] == "false"
        assert env["OAUTH2_PROXY_EMAIL_DOMAINS"] == "*"


class TestGetExtraJWTIssuers:
    action_name = "get-extra-jwt-issuers"

    def test_get_extra_jwt_issuers(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        oauth_relation: ops.testing.Relation,
        oauth_secret: ops.testing.Secret,
        mocked_oauth2_proxy_is_running: MagicMock,
    ) -> None:
        state_in = create_state(
            relations=[peer_relation, oauth_relation],
            secrets=[oauth_secret],
            config={"enable_jwt_bearer_tokens": True}
        )

        context.run(context.on.action(self.action_name), state_in)
        results = context.action_results

        extra_jwt_issuers_list = results["extra-jwt-issuers"]

        assert len(extra_jwt_issuers_list) == 1
        assert extra_jwt_issuers_list[0]["oidc-issuer-url"] == "https://example.oidc.com"

        assert extra_jwt_issuers_list[0]["audience"] == OAUTH_CLIENT_ID

    def test_get_extra_jwt_issuers_when_not_enabled(
        self,
        context: ops.testing.Context,
        peer_relation: ops.testing.PeerRelation,
        oauth_relation: ops.testing.Relation,
        oauth_secret: ops.testing.Secret,
        mocked_oauth2_proxy_is_running: MagicMock,
    ) -> None:
        state_in = create_state(
            relations=[peer_relation, oauth_relation],
            secrets=[oauth_secret],
        )

        with pytest.raises(ops.testing.ActionFailed) as exc_info:
            context.run(context.on.action(self.action_name), state_in)

        assert "`enable_jwt_bearer_tokens` is not enabled" in exc_info.value.message
