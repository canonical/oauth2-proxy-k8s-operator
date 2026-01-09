# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration tests."""

import logging
from os.path import join
from pathlib import Path

import jubilant
import pytest
import requests
from lightkube import Client
from tenacity import retry, stop_after_attempt, wait_exponential

from tests.integration.constants import (
    APP_NAME,
    AUTH_PROXY_REQUIRER,
    CERTIFICATES_PROVIDER,
    IMAGE_PATH,
    TRAEFIK,
)
from tests.integration.utils import (
    get_reverse_proxy_app_url,
    remove_integration,
    wait_for_active_idle,
)

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
def test_build_and_deploy(model: jubilant.Juju, local_charm: Path) -> None:
    """Build and deploy oauth2-proxy."""
    model.deploy(
        charm=str(local_charm),
        app=APP_NAME,
        resources={"oauth2-proxy-image": IMAGE_PATH},
        trust=True,
    )

    wait_for_active_idle(model, apps=[APP_NAME], timeout=1000)


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
def test_ingress_relation(model: jubilant.Juju) -> None:
    model.deploy(
        TRAEFIK,
        channel="latest/edge",
        trust=True,
    )

    model.integrate(f"{APP_NAME}:ingress", TRAEFIK)
    wait_for_active_idle(model, apps=[APP_NAME, TRAEFIK], timeout=1000)


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
def test_receive_certs_relation(model: jubilant.Juju) -> None:
    model.deploy(
        CERTIFICATES_PROVIDER,
        channel="latest/stable",
        trust=True,
    )

    model.integrate(f"{APP_NAME}:receive-ca-cert", CERTIFICATES_PROVIDER)
    wait_for_active_idle(model, apps=[APP_NAME, CERTIFICATES_PROVIDER], timeout=1000)


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=20),
    stop=stop_after_attempt(10),
    reraise=True,
)
def test_health_checks(model: jubilant.Juju, lightkube_client: Client) -> None:
    base_url = get_reverse_proxy_app_url(model, TRAEFIK, APP_NAME, lightkube_client)

    health_check_url = join(base_url, "ping")

    resp = requests.get(health_check_url, timeout=300, verify=False)
    assert resp.status_code == 200

    response = requests.get(base_url, timeout=300, verify=False)
    assert response.status_code == 403


@pytest.mark.abort_on_fail
def test_auth_proxy_relation(model: jubilant.Juju, requirer_charm: Path) -> None:
    """Ensure that oauth2-proxy is able to provide auth-proxy relation."""
    model.deploy(
        charm=str(requirer_charm),
        app=AUTH_PROXY_REQUIRER,
        resources={"oci-image": "kennethreitz/httpbin"},
        trust=True,
    )

    model.integrate(f"{AUTH_PROXY_REQUIRER}:ingress", TRAEFIK)
    model.integrate(f"{AUTH_PROXY_REQUIRER}:auth-proxy", APP_NAME)

    wait_for_active_idle(
        model,
        apps=[APP_NAME, AUTH_PROXY_REQUIRER, TRAEFIK],
        timeout=1000
    )


@pytest.mark.abort_on_fail
def test_forward_auth_relation(model: jubilant.Juju) -> None:
    """Ensure that oauth2-proxy is able to provide forward-auth relation."""
    model.config(TRAEFIK, {"enable_experimental_forward_auth": "True"})
    model.integrate(f"{TRAEFIK}:experimental-forward-auth", APP_NAME)

    wait_for_active_idle(model, apps=[APP_NAME, TRAEFIK], timeout=1000)


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=20),
    stop=stop_after_attempt(10),
    reraise=True,
)
def test_allowed_forward_auth_url_redirect(model: jubilant.Juju, lightkube_client: Client) -> None:
    """Test that a request hitting a protected application is forwarded by traefik to oauth2 proxy.

    An allowed request should be performed without authentication.
    Retry the request to ensure the right config was populated to oauth2 proxy.
    """
    requirer_url = get_reverse_proxy_app_url(model, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client)

    protected_url = join(requirer_url, "anything/allowed")

    resp = requests.get(protected_url, verify=False)
    assert resp.status_code == 200


def test_protected_forward_auth_url_redirect(model: jubilant.Juju, lightkube_client: Client) -> None:
    """Test reaching a protected url.

    The request should be forwarded by traefik to oauth2 proxy.
    An unauthenticated request should then be denied with 403 response.
    """
    requirer_url = get_reverse_proxy_app_url(model, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client)

    protected_url = join(requirer_url, "anything/deny")

    resp = requests.get(protected_url, verify=False)
    assert resp.status_code == 403


def test_oauth2_proxy_scale_up(model: jubilant.Juju) -> None:
    """Check that OAuth2 Proxy works after it is scaled up."""
    model.cli("scale-application", APP_NAME, "2")
    wait_for_active_idle(model, apps=[APP_NAME], timeout=1000)


def test_oauth2_proxy_scale_down(model: jubilant.Juju) -> None:
    """Check that OAuth2 Proxy works after it is scaled down."""
    model.cli("scale-application", APP_NAME, "1")
    wait_for_active_idle(model, apps=[APP_NAME], timeout=1000)


def test_remove_forward_auth_integration(model: jubilant.Juju) -> None:
    """Ensure that the forward-auth relation doesn't cause errors on removal."""
    with remove_integration(model, TRAEFIK, "forward-auth"):
        wait_for_active_idle(model, apps=[APP_NAME, TRAEFIK], timeout=1000)


def test_remove_auth_proxy_integration(model: jubilant.Juju) -> None:
    """Ensure that the auth-proxy relation doesn't cause errors on removal."""
    with remove_integration(model, AUTH_PROXY_REQUIRER, "auth-proxy"):
        wait_for_active_idle(model, apps=[APP_NAME, AUTH_PROXY_REQUIRER], timeout=1000)
