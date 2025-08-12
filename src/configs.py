# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any, Mapping, TypeAlias

from ops import ConfigData

from env_vars import EnvVars

ServiceConfigs: TypeAlias = Mapping[str, Any]


class CharmConfig:
    """A class representing the data source of charm configurations."""

    def __init__(self, config: ConfigData) -> None:
        self._config = config

    def __getitem__(self, key: str) -> Any:
        return self._config.get(key)

    def to_env_vars(self) -> EnvVars:
        return {
            "OAUTH2_PROXY_SSL_INSECURE_SKIP_VERIFY": "true" if self._config["dev"] else "false",
        }
