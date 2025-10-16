# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
from collections import ChainMap

from ops import Unit
from ops.pebble import Layer, LayerDict

from constants import (
    OAUTH2_PROXY_API_PORT,
    PEBBLE_READY_CHECK_NAME,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleServiceError

logger = logging.getLogger(__name__)

PEBBLE_LAYER_DICT = {
    "summary": "oauth2 proxy layer",
    "description": "pebble config layer for oauth2-proxy-k8s-operator",
    "services": {
        WORKLOAD_SERVICE: {
            "summary": WORKLOAD_SERVICE,
            "command": "/bin/oauth2-proxy",
            "startup": "enabled",
            "override": "replace",
            "on-check-failure": {PEBBLE_READY_CHECK_NAME: "ignore"},
        }
    },
    "checks": {
        PEBBLE_READY_CHECK_NAME: {
            "override": "replace",
            "period": "10s",
            "http": {"url": f"http://localhost:{OAUTH2_PROXY_API_PORT}/ready"},
        }
    },
}


class PebbleService:
    """Pebble service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit
        self._container = unit.get_container(WORKLOAD_CONTAINER)
        self._layer_dict: LayerDict = PEBBLE_LAYER_DICT

    def plan(self, layer: Layer) -> None:
        self._container.add_layer(WORKLOAD_CONTAINER, layer, combine=True)

        try:
            self._container.replan()
        except Exception as e:
            logger.error(f"Failed to replan the workload service: {e}")
            raise PebbleServiceError("Pebble failed to replan the workload service")

    def render_pebble_layer(self, *env_var_sources: EnvVarConvertible) -> Layer:
        proxy_env_vars = {
            "HTTP_PROXY": os.environ.get("HTTP_PROXY"),
            "HTTPS_PROXY": os.environ.get("HTTPS_PROXY"),
            "NO_PROXY": os.environ.get("NO_PROXY"),
        }

        updated_env_vars = ChainMap(*(source.to_env_vars() for source in env_var_sources))  # type: ignore

        env_vars = {
            **DEFAULT_CONTAINER_ENV,
            **proxy_env_vars,
            **updated_env_vars,
        }

        if env_vars.get("OAUTH2_PROXY_SKIP_JWT_BEARER_TOKENS") == "true":
            env_vars["OAUTH2_PROXY_EXTRA_JWT_ISSUERS"] = (
                f"{env_vars['OAUTH2_PROXY_OIDC_ISSUER_URL']}={env_vars['OAUTH2_PROXY_CLIENT_ID']}"
            )

        self._layer_dict["services"][WORKLOAD_SERVICE]["environment"] = env_vars

        return Layer(self._layer_dict)
