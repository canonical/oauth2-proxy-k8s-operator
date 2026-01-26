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
    all_active,
    and_,
    any_error,
    get_reverse_proxy_app_url,
    remove_integration,
    unit_number,
)

logger = logging.getLogger(__name__)


@pytest.mark.setup
def test_build_and_deploy(juju: jubilant.Juju, local_charm: Path) -> None:
    """Build and deploy oauth2-proxy."""
    juju.deploy(
        charm=str(local_charm),
        app=APP_NAME,
        resources={"oauth2-proxy-image": IMAGE_PATH},
        trust=True,
    )

    juju.wait(
        ready=all_active(APP_NAME),
        error=any_error(APP_NAME),
        timeout=10 * 60,
    )


@pytest.mark.setup
def test_ingress_relation(juju: jubilant.Juju) -> None:
    juju.deploy(
        TRAEFIK,
        channel="latest/edge",
        revision=263,
        trust=True,
    )

    juju.integrate(f"{APP_NAME}:ingress", TRAEFIK)
    juju.wait(
        ready=all_active(APP_NAME, TRAEFIK),
        error=any_error(APP_NAME, TRAEFIK),
        timeout=10 * 60,
    )


@pytest.mark.setup
def test_receive_certs_relation(juju: jubilant.Juju) -> None:
    juju.deploy(
        CERTIFICATES_PROVIDER,
        channel="latest/stable",
        trust=True,
    )

    juju.integrate(f"{APP_NAME}:receive-ca-cert", CERTIFICATES_PROVIDER)
    juju.wait(
        ready=all_active(APP_NAME, CERTIFICATES_PROVIDER),
        error=any_error(APP_NAME, CERTIFICATES_PROVIDER),
        timeout=10 * 60,
    )


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=20),
    stop=stop_after_attempt(10),
    reraise=True,
)
def test_health_checks(juju: jubilant.Juju, lightkube_client: Client) -> None:
    base_url = get_reverse_proxy_app_url(juju, TRAEFIK, APP_NAME, lightkube_client)

    health_check_url = join(base_url, "ping")

    resp = requests.get(health_check_url, timeout=300, verify=False)
    assert resp.status_code == 200

    response = requests.get(base_url, timeout=300, verify=False)
    assert response.status_code == 403


@pytest.mark.setup
def test_auth_proxy_relation(juju: jubilant.Juju, requirer_charm: Path) -> None:
    """Ensure that oauth2-proxy is able to provide auth-proxy relation."""
    juju.deploy(
        charm=str(requirer_charm),
        app=AUTH_PROXY_REQUIRER,
        resources={"oci-image": "kennethreitz/httpbin"},
        trust=True,
    )

    juju.integrate(f"{AUTH_PROXY_REQUIRER}:ingress", TRAEFIK)
    juju.integrate(f"{AUTH_PROXY_REQUIRER}:auth-proxy", APP_NAME)

    juju.wait(
        ready=all_active(APP_NAME, AUTH_PROXY_REQUIRER, TRAEFIK),
        error=any_error(APP_NAME, AUTH_PROXY_REQUIRER, TRAEFIK),
        timeout=10 * 60,
    )


def test_forward_auth_relation(juju: jubilant.Juju) -> None:
    """Ensure that oauth2-proxy is able to provide forward-auth relation."""
    juju.config(TRAEFIK, {"enable_experimental_forward_auth": "True"})
    juju.integrate(f"{TRAEFIK}:experimental-forward-auth", APP_NAME)

    juju.wait(
        ready=all_active(APP_NAME, TRAEFIK),
        error=any_error(APP_NAME, TRAEFIK),
        timeout=10 * 60,
    )


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=20),
    stop=stop_after_attempt(10),
    reraise=True,
)
def test_allowed_forward_auth_url_redirect(juju: jubilant.Juju, lightkube_client: Client) -> None:
    """Test that a request hitting a protected application is forwarded by traefik to oauth2 proxy.

    An allowed request should be performed without authentication.
    Retry the request to ensure the right config was populated to oauth2 proxy.
    """
    requirer_url = get_reverse_proxy_app_url(juju, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client)

    protected_url = join(requirer_url, "anything/allowed")

    resp = requests.get(protected_url, verify=False)
    assert resp.status_code == 200


def test_protected_forward_auth_url_redirect(juju: jubilant.Juju, lightkube_client: Client) -> None:
    """Test reaching a protected url.

    The request should be forwarded by traefik to oauth2 proxy.
    An unauthenticated request should then be denied with 403 response.
    """
    requirer_url = get_reverse_proxy_app_url(juju, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client)

    protected_url = join(requirer_url, "anything/deny")

    resp = requests.get(protected_url, verify=False)
    assert resp.status_code == 403


def test_oauth2_proxy_scale_up(juju: jubilant.Juju) -> None:
    """Check that OAuth2 Proxy works after it is scaled up."""
    juju.cli("scale-application", APP_NAME, "2")
    juju.wait(
        ready=and_(
            all_active(APP_NAME),
            unit_number(app=APP_NAME, expected_num=2),
        ),
        error=any_error(APP_NAME),
        timeout=10 * 60,
    )


def test_remove_forward_auth_integration(juju: jubilant.Juju) -> None:
    """Ensure that the forward-auth relation doesn't cause errors on removal."""
    with remove_integration(juju, TRAEFIK, "forward-auth"):
        juju.wait(
            ready=all_active(APP_NAME, TRAEFIK),
            error=any_error(APP_NAME, TRAEFIK),
            timeout=10 * 60,
        )


def test_remove_auth_proxy_integration(juju: jubilant.Juju) -> None:
    """Ensure that the auth-proxy relation doesn't cause errors on removal."""
    with remove_integration(juju, AUTH_PROXY_REQUIRER, "auth-proxy"):
        juju.wait(
            ready=all_active(APP_NAME, AUTH_PROXY_REQUIRER),
            error=any_error(APP_NAME, AUTH_PROXY_REQUIRER),
            timeout=10 * 60,
        )


def test_oauth2_proxy_scale_down(juju: jubilant.Juju) -> None:
    """Check that OAuth2 Proxy works after it is scaled down."""
    juju.cli("scale-application", APP_NAME, "1")
    juju.wait(
        ready=and_(
            all_active(APP_NAME),
            unit_number(app=APP_NAME, expected_num=1),
        ),
        error=any_error(APP_NAME),
        timeout=10 * 60,
    )
