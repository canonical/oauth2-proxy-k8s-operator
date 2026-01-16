# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Any
from unittest.mock import MagicMock, create_autospec

import ops.testing
import pytest
from ops.model import Container
from ops.pebble import Layer
from pytest_mock import MockerFixture

from charm import Oauth2ProxyK8sOperatorCharm
from constants import WORKLOAD_CONTAINER
from services import PEBBLE_LAYER_DICT

APP_NAME = "oauth2-proxy-k8s"
COOKIE_SECRET = "0123456789abcdef0123456789abcdef"
MODEL_NAME = "testing"
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
OAUTH_SECRET_ID = "secret:hydra-test-secret-123"
AUTH_PROXY_CONFIG = {
    "protected_urls": ["https://example.com"],
    "allowed_endpoints": ["welcome", "about/app"],
    "headers": ["X-Auth-Request-User"],
    "authenticated_emails": ["test@canonical.com"],
    "authenticated_email_domains": ["example.com"],
}
FORWARD_AUTH_CONFIG = {
    "decisions_address": "https://oauth2-proxy-k8s.testing.svc.cluster.local:4180",
    "app_names": ["charmed-app"],
    "headers": ["X-Auth-Request-User"],
}
FORWARD_AUTH_REQUIRER_CONFIG = {
    "ingress_app_names": ["charmed-app"],
}


@pytest.fixture
def context() -> ops.testing.Context:
    return ops.testing.Context(Oauth2ProxyK8sOperatorCharm)


def dict_to_relation_data(dic: dict[str, Any]) -> dict[str, str]:
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


def create_state(
    *,
    leader: bool = True,
    can_connect: bool = True,
    config: dict[str, Any] | None = None,
    container: ops.testing.Container | None = None,
    relations: list[ops.testing.Relation] | None = None,
    secrets: list[ops.testing.Secret] | None = None,
) -> ops.testing.State:
    """Factory function to create charm state with explicit parameters.

    Args:
        leader: Whether this unit is the leader
        can_connect: Whether the workload container can connect (ignored if container provided)
        config: Charm configuration to set
        container: Custom container to use (overrides can_connect if provided)
        relations: List of relations to include in the state
        secrets: List of secrets to include in the state
    """
    if container is None:
        container = ops.testing.Container(
            name=WORKLOAD_CONTAINER,
            can_connect=can_connect,
            execs={
                ops.testing.Exec(
                    ["/bin/oauth2-proxy", "--version"],
                    return_code=0,
                    stdout="v7.8.1",
                )
            } if can_connect else {},
        )

    return ops.testing.State(
        containers=[container],
        config=config or {},
        leader=leader,
        model=ops.testing.Model(name=MODEL_NAME),
        relations=relations or [],
        secrets=secrets or [],
    )


@pytest.fixture
def expected_pebble_layer() -> Layer:
    return Layer(PEBBLE_LAYER_DICT)


@pytest.fixture
def peer_relation() -> ops.testing.PeerRelation:
    return ops.testing.PeerRelation(
        endpoint="oauth2-proxy",
        interface="oauth2_proxy_peers",
        local_app_data={"cookies_key": json.dumps(COOKIE_SECRET)},
    )


@pytest.fixture
def ingress_relation() -> ops.testing.Relation:
    url = f"http://ingress:80/{MODEL_NAME}-{APP_NAME}"
    return ops.testing.Relation(
        endpoint="ingress",
        interface="ingress",
        remote_app_name="traefik",
        remote_app_data={"url": url},
    )


@pytest.fixture
def oauth_secret() -> ops.testing.Secret:
    """Creates the Secret object containing the client_secret."""
    return ops.testing.Secret(
        id=OAUTH_SECRET_ID,
        label="hydra-oauth-secret",
        tracked_content={"secret": OAUTH_CLIENT_SECRET},
        owner="remote",
    )


@pytest.fixture
def oauth_relation() -> ops.testing.Relation:
    return ops.testing.Relation(
        endpoint="oauth",
        interface="oauth",
        remote_app_name="hydra",
        remote_app_data={
            "client_id": OAUTH_CLIENT_ID,
            "client_secret_id": OAUTH_SECRET_ID,
            **OAUTH_PROVIDER_INFO,
        },
        local_app_data={
            "audience": "[]",
            "redirect_uri": "http://oauth2-proxy-k8s.testing.svc.cluster.local:4180/oauth2/callback",
            "scope": "openid email profile offline_access",
            "token_endpoint_auth_method": "client_secret_basic",
            "grant_types": '["authorization_code", "refresh_token"]',
        },
    )


@pytest.fixture
def auth_proxy_relation() -> ops.testing.Relation:
    return ops.testing.Relation(
        endpoint="auth-proxy",
        interface="auth_proxy",
        remote_app_name="requirer",
        remote_app_data=dict_to_relation_data(AUTH_PROXY_CONFIG),
    )


@pytest.fixture
def forward_auth_relation() -> ops.testing.Relation:
    return ops.testing.Relation(
        endpoint="forward-auth",
        interface="forward_auth",
        remote_app_name="traefik",
        local_app_data=dict_to_relation_data(FORWARD_AUTH_CONFIG),
        remote_app_data=dict_to_relation_data(FORWARD_AUTH_REQUIRER_CONFIG),
    )


@pytest.fixture
def certificates_relation() -> ops.testing.Relation:
    return ops.testing.Relation(
        endpoint="receive-ca-cert",
        interface="certificate_transfer",
        remote_app_name="self-signed-certificates",
    )


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture) -> None:
    mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace=MODEL_NAME,
        _patch=lambda *a, **kw: True,
        is_ready=lambda *a, **kw: True,
    )


@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


@pytest.fixture()
def mocked_oauth2_proxy_is_running(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.Oauth2ProxyK8sOperatorCharm._oauth2_proxy_service_is_running", return_value=True
    )


@pytest.fixture
def mocked_forward_auth_update(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charms.oauth2_proxy_k8s.v0.forward_auth.ForwardAuthProvider.update_forward_auth_config"
    )


@pytest.fixture(autouse=True)
def mocked_push_ca_certs(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "integrations.TrustedCertificatesTransferIntegration._push_ca_certs", return_value=None
    )
