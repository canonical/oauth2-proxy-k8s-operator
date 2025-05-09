# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration tests."""

import logging
from os.path import join
from pathlib import Path
from typing import Optional

import pytest
import requests
import yaml
from lightkube import ApiError, Client
from lightkube.resources.core_v1 import Service
from pytest_operator.plugin import OpsTest
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
IMAGE_PATH = METADATA["resources"]["oauth2-proxy-image"]["upstream-source"]
TRAEFIK = "traefik-k8s"
CERTIFICATES_PROVIDER = "self-signed-certificates"
AUTH_PROXY_REQUIRER = "auth-proxy-requirer"


async def get_k8s_service_address(
    ops_test: OpsTest, service_name: str, lightkube_client: Client
) -> Optional[str]:
    """Get the address of a LoadBalancer Kubernetes service using kubectl."""
    try:
        result = lightkube_client.get(Service, name=service_name, namespace=ops_test.model.name)
        ip_address = result.status.loadBalancer.ingress[0].ip
        return ip_address
    except ApiError as e:
        logger.error(f"Error retrieving service address: {e}")
        return None


async def get_reverse_proxy_app_url(
    ops_test: OpsTest, ingress_app_name: str, app_name: str, lightkube_client: Client
) -> str:
    """Get the ingress address of an app."""
    address = await get_k8s_service_address(ops_test, f"{ingress_app_name}-lb", lightkube_client)
    proxy_app_url = f"http://{address}/{ops_test.model.name}-{app_name}/"
    logger.debug(f"Retrieved address: {proxy_app_url}")
    return proxy_app_url


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, local_charm: Path) -> None:
    """Build and deploy oauth2-proxy."""
    await ops_test.model.deploy(
        application_name=APP_NAME,
        entity_url=str(local_charm),
        resources={"oauth2-proxy-image": IMAGE_PATH},
        series="jammy",
        trust=True,
    )

    await ops_test.model.wait_for_idle(
        raise_on_blocked=False,
        raise_on_error=True,
        status="active",
        timeout=1000,
    )
    assert ops_test.model.applications[APP_NAME].units[0].workload_status == "active"


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_ingress_relation(ops_test: OpsTest) -> None:
    await ops_test.model.deploy(
        TRAEFIK,
        channel="latest/edge",
        trust=True,
    )

    await ops_test.model.integrate(f"{APP_NAME}:ingress", TRAEFIK)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, TRAEFIK],
        status="active",
        raise_on_blocked=False,
        timeout=1000,
    )


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_receive_certs_relation(ops_test: OpsTest) -> None:
    await ops_test.model.deploy(
        CERTIFICATES_PROVIDER,
        channel="latest/stable",
        trust=True,
    )

    await ops_test.model.integrate(f"{APP_NAME}:receive-ca-cert", CERTIFICATES_PROVIDER)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, CERTIFICATES_PROVIDER],
        status="active",
        raise_on_blocked=False,
        timeout=1000,
    )


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=20),
    stop=stop_after_attempt(10),
    reraise=True,
)
async def test_health_checks(ops_test: OpsTest, lightkube_client: Client) -> None:
    base_url = await get_reverse_proxy_app_url(ops_test, TRAEFIK, APP_NAME, lightkube_client)

    health_check_url = join(base_url, "ping")

    resp = requests.get(health_check_url, timeout=300, verify=False)
    assert resp.status_code == 200

    response = requests.get(base_url, timeout=300, verify=False)
    assert response.status_code == 403


@pytest.mark.abort_on_fail
async def test_auth_proxy_relation(ops_test: OpsTest) -> None:
    """Ensure that oauth2-proxy is able to provide auth-proxy relation."""
    requirer_charm_path = Path(f"tests/integration/{AUTH_PROXY_REQUIRER}").absolute()
    requirer_charm = await ops_test.build_charm(requirer_charm_path, verbosity="debug")

    await ops_test.model.deploy(
        application_name=AUTH_PROXY_REQUIRER,
        entity_url=requirer_charm,
        resources={"oci-image": "kennethreitz/httpbin"},
        series="jammy",
        trust=True,
    )

    await ops_test.model.integrate(f"{AUTH_PROXY_REQUIRER}:ingress", TRAEFIK)
    await ops_test.model.integrate(f"{AUTH_PROXY_REQUIRER}:auth-proxy", APP_NAME)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME, AUTH_PROXY_REQUIRER, TRAEFIK],
        status="active",
        raise_on_blocked=False,
        timeout=1000,
    )


@pytest.mark.abort_on_fail
async def test_forward_auth_relation(ops_test: OpsTest) -> None:
    """Ensure that oauth2-proxy is able to provide forward-auth relation."""
    await ops_test.model.applications[TRAEFIK].set_config({
        "enable_experimental_forward_auth": "True"
    })
    await ops_test.model.integrate(f"{TRAEFIK}:experimental-forward-auth", APP_NAME)

    await ops_test.model.wait_for_idle([TRAEFIK, APP_NAME], status="active", timeout=1000)


@retry(
    wait=wait_exponential(multiplier=3, min=1, max=20),
    stop=stop_after_attempt(10),
    reraise=True,
)
async def test_allowed_forward_auth_url_redirect(
    ops_test: OpsTest, lightkube_client: Client
) -> None:
    """Test that a request hitting a protected application is forwarded by traefik to oauth2 proxy.

    An allowed request should be performed without authentication.
    Retry the request to ensure the right config was populated to oauth2 proxy.
    """
    requirer_url = await get_reverse_proxy_app_url(
        ops_test, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client
    )

    protected_url = join(requirer_url, "anything/allowed")

    resp = requests.get(protected_url, verify=False)
    assert resp.status_code == 200


async def test_protected_forward_auth_url_redirect(
    ops_test: OpsTest, lightkube_client: Client
) -> None:
    """Test reaching a protected url.

    The request should be forwarded by traefik to oauth2 proxy.
    An unauthenticated request should then be denied with 403 response.
    """
    requirer_url = await get_reverse_proxy_app_url(
        ops_test, TRAEFIK, AUTH_PROXY_REQUIRER, lightkube_client
    )

    protected_url = join(requirer_url, "anything/deny")

    resp = requests.get(protected_url, verify=False)
    assert resp.status_code == 403


async def test_oauth2_proxy_scale_up(ops_test: OpsTest) -> None:
    """Check that OAuth2 Proxy works after it is scaled up."""
    app = ops_test.model.applications[APP_NAME]

    await app.scale(2)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=False,
        timeout=1000,
        wait_for_active=True,
    )


async def test_oauth2_proxy_scale_down(ops_test: OpsTest) -> None:
    """Check that OAuth2 Proxy works after it is scaled down."""
    app = ops_test.model.applications[APP_NAME]

    await app.scale(1)

    await ops_test.model.wait_for_idle(
        apps=[APP_NAME],
        status="active",
        raise_on_blocked=False,
        timeout=1000,
        wait_for_active=True,
    )


async def test_remove_forward_auth_integration(ops_test: OpsTest) -> None:
    """Ensure that the forward-auth relation doesn't cause errors on removal."""
    await ops_test.juju("remove-relation", APP_NAME, f"{TRAEFIK}:experimental-forward-auth")

    await ops_test.model.wait_for_idle([TRAEFIK, APP_NAME], status="active")


async def test_remove_auth_proxy_integration(ops_test: OpsTest) -> None:
    """Ensure that the auth-proxy relation doesn't cause errors on removal."""
    await ops_test.juju("remove-relation", APP_NAME, f"{AUTH_PROXY_REQUIRER}:auth-proxy")

    await ops_test.model.wait_for_idle([AUTH_PROXY_REQUIRER, APP_NAME], status="active")
