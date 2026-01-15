# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

import jubilant
from lightkube import ApiError, Client
from lightkube.resources.core_v1 import Service
from tenacity import retry, stop_after_attempt, wait_exponential

from tests.integration.constants import APP_NAME

logger = logging.getLogger(__name__)

StatusPredicate = Callable[[jubilant.Status], bool]


def juju_model_factory(model_name: str) -> jubilant.Juju:
    juju = jubilant.Juju()
    try:
        juju.add_model(model_name, config={"logging-config": "<root>=INFO"})
    except jubilant.CLIError as e:
        if "already exists" not in e.stderr:
            raise

        juju.model = model_name

    return juju


def get_k8s_service_address(juju: jubilant.Juju, service_name: str, lightkube_client: Client) -> Optional[str]:
    """Get the address of a LoadBalancer Kubernetes service using kubectl."""
    try:
        result = lightkube_client.get(Service, name=service_name, namespace=juju.model)
        ip_address = result.status.loadBalancer.ingress[0].ip
        return ip_address
    except ApiError as e:
        logger.error(f"Error retrieving service address: {e}")
        return None


def get_reverse_proxy_app_url(juju: jubilant.Juju, ingress_app_name: str, app_name: str, lightkube_client: Client) -> str:
    """Get the ingress address of an app."""
    address = get_k8s_service_address(juju, f"{ingress_app_name}-lb", lightkube_client)
    proxy_app_url = f"http://{address}/{juju.model}-{app_name}/"
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


def all_active(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_active(status, *apps)


def all_blocked(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_blocked(status, *apps)


def any_error(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.any_error(status, *apps)


def is_active(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_active


def is_blocked(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_blocked


def unit_number(app: str, expected_num: int) -> StatusPredicate:
    return lambda status: len(status.apps[app].units) == expected_num


def and_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: all(predicate(status) for predicate in predicates)


def or_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: any(predicate(status) for predicate in predicates)
