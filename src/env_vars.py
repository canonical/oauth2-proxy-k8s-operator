# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Mapping, Protocol, TypeAlias, Union

from constants import OAUTH2_PROXY_API_PORT

EnvVars: TypeAlias = Mapping[str, Union[str, bool, list]]

DEFAULT_CONTAINER_ENV = {
    "OAUTH2_PROXY_HTTP_ADDRESS": f"0.0.0.0:{OAUTH2_PROXY_API_PORT}",
    "OAUTH2_PROXY_SSL_INSECURE_SKIP_VERIFY": "false",
    "OAUTH2_PROXY_CLIENT_ID": "default",
    "OAUTH2_PROXY_CLIENT_SECRET": "default",
    "OAUTH2_PROXY_EMAIL_DOMAINS": "*",
    "OAUTH2_PROXY_SET_XAUTHREQUEST": "true",
    "OAUTH2_PROXY_REVERSE_PROXY": "true",
    "OAUTH2_PROXY_UPSTREAMS": "static://200",
}


class EnvVarConvertible(Protocol):
    """An interface enforcing the contribution to workload service environment variables."""

    def to_env_vars(self) -> EnvVars:
        pass
