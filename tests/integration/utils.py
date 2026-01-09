# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from contextlib import contextmanager
from typing import Iterator, Optional

import jubilant
import pytest
from lightkube import ApiError, Client
from lightkube.resources.core_v1 import Service
from tenacity import retry, stop_after_attempt, wait_exponential

from tests.integration.constants import APP_NAME

logger = logging.getLogger(__name__)


def create_temp_juju_model(
    request: pytest.FixtureRequest, *, model: str = ""
) -> Iterator[jubilant.Juju]:
    """Create a temporary Juju model."""
    keep_models = bool(request.config.getoption("--keep-models"))

    # jubilant.temp_model is a context manager provided by the library
    with jubilant.temp_model(keep=keep_models) as juju:
        # Hack to get around `jubilant.temp_model` not accepting a custom model name
        if model:
            assert juju.model is not None
            # Destroy `jubilant-*` model created by default
            juju.destroy_model(juju.model, destroy_storage=True, force=True)

            # `CLIError` will be emitted if `--model` already exists so silently ignore
            # error and set the `model` attribute to the value of model.
            try:
                juju.add_model(model)
            except jubilant.CLIError:
                juju.model = model

        juju.wait_timeout = 10 * 60

        yield juju

        if request.session.testsfailed:
            log = juju.debug_log(limit=1000)
            print(log, end="")


def wait_for_active_idle(model: jubilant.Juju, apps: list[str], timeout: float = 1000) -> None:
    """Wait for all applications and their units to be active and idle."""

    def condition(s: jubilant.Status) -> bool:
        return jubilant.all_active(s, *apps) and jubilant.all_agents_idle(s, *apps)

    model.wait(condition, error=jubilant.any_error, timeout=timeout)


def wait_for_status(
    model: jubilant.Juju, apps: list[str], status: str, timeout: float = 1000
) -> None:
    """Wait for all applications and their units to reach the given status."""

    def condition(s: jubilant.Status) -> bool:
        return all(s.apps[app_name].app_status.current == status for app_name in apps)

    model.wait(condition, timeout=timeout)


def get_k8s_service_address(model: jubilant.Juju, service_name: str, lightkube_client: Client) -> Optional[str]:
    """Get the address of a LoadBalancer Kubernetes service using kubectl."""
    try:
        result = lightkube_client.get(Service, name=service_name, namespace=model.model)
        ip_address = result.status.loadBalancer.ingress[0].ip
        return ip_address
    except ApiError as e:
        logger.error(f"Error retrieving service address: {e}")
        return None


def get_reverse_proxy_app_url(model: jubilant.Juju, ingress_app_name: str, app_name: str, lightkube_client: Client) -> str:
    """Get the ingress address of an app."""
    address = get_k8s_service_address(model, f"{ingress_app_name}-lb", lightkube_client)
    proxy_app_url = f"http://{address}/{model.model}-{app_name}/"
    logger.debug(f"Retrieved address: {proxy_app_url}")
    return proxy_app_url


@contextmanager
def remove_integration(
    juju: jubilant.Juju, /, remote_app_name: str, integration_name: str
) -> Iterator[None]:
    """Temporarily remove an integration from the application.

    Integration is restored after the context is exited.
    """

    # The pre-existing integration instance can still be "dying" when the `finally` block
    # is called, so `tenacity.retry` is used here to capture the `jubilant.CLIError`
    # and re-run `juju integrate ...` until the previous integration instance has finished dying.
    @retry(
        wait=wait_exponential(multiplier=2, min=1, max=30),
        stop=stop_after_attempt(10),
        reraise=True,
    )
    def _reintegrate() -> None:
        juju.integrate(f"{APP_NAME}:{integration_name}", remote_app_name)

    juju.remove_relation(f"{APP_NAME}:{integration_name}", remote_app_name)
    try:
        yield
    finally:
        _reintegrate()
