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
        env_vars = {
            "OAUTH2_PROXY_SSL_INSECURE_SKIP_VERIFY": "true" if self._config["dev"] else "false"
        }

        if self._config["enable_jwt_bearer_tokens"]:
            env_vars["OAUTH2_PROXY_SKIP_JWT_BEARER_TOKENS"] = "true"
            env_vars["OAUTH2_PROXY_EXTRA_JWT_ISSUERS"] = (
                "${OAUTH2_PROXY_OIDC_ISSUER_URL}=${OAUTH2_PROXY_CLIENT_ID}"
            )
            env_vars["OAUTH2_PROXY_BEARER_TOKEN_LOGIN_FALLBACK"] = "false"
            env_vars["OAUTH2_PROXY_EMAIL_DOMAINS"] = "*"

        return env_vars
