# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

# flake8: noqa

"""Charm integration test helpers."""

import logging
import socket
from pathlib import Path

import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
CHARM_CONFIG = {
    "upstream": "http://upstream",
    "client-id": "client-id",
    "client-secret": "client-secret",
    "cookie-secret": "2YM3DvbcSVdlsPl3HHaibQdCnefGeq5gVNi4-lVX6IQ=", # sample
}


def gen_patch_getaddrinfo(host: str, resolve_to: str):  # noqa
    """Generate patched getaddrinfo function.

    This function is used to generate a patched getaddrinfo function that will resolve to the
    resolve_to address without having to actually register a host.

    Args:
        host: intended hostname of a given application.
        resolve_to: destination address for host to resolve to.
    Returns:
        A patching function for getaddrinfo.
    """
    original_getaddrinfo = socket.getaddrinfo

    def patched_getaddrinfo(*args):
        """Patch getaddrinfo to point to desired ip address.

        Args:
            args: original arguments to getaddrinfo when creating network connection.
        Returns:
            Patched getaddrinfo function.
        """
        if args[0] == host:
            return original_getaddrinfo(resolve_to, *args[1:])
        return original_getaddrinfo(*args)

    return patched_getaddrinfo


async def get_unit_url(ops_test: OpsTest, application, unit, port, protocol="http"):
    """Return unit URL from the model.

    Args:
        ops_test: PyTest object.
        application: Name of the application.
        unit: Number of the unit.
        port: Port number of the URL.
        protocol: Transfer protocol (default: http).

    Returns:
        Unit URL of the form {protocol}://{address}:{port}
    """
    status = await ops_test.model.get_status()  # noqa: F821
    address = status["applications"][application]["units"][f"{application}/{unit}"]["address"]
    return f"{protocol}://{address}:{port}"
