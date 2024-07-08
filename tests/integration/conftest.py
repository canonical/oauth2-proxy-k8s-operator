# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm integration test config."""

import asyncio
import logging

import pytest_asyncio
from helpers import APP_NAME, CHARM_CONFIG, METADATA
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture(name="deploy", scope="module")
async def deploy(ops_test: OpsTest):
    """Test the app is up and running."""
    charm = await ops_test.build_charm(".")
    resources = {"oauth2-proxy-image": METADATA["resources"]["oauth2-proxy-image"]["upstream-source"]}

    asyncio.gather(
        ops_test.model.deploy(charm, resources=resources, application_name=APP_NAME, config=CHARM_CONFIG),
        ops_test.model.deploy("nginx-ingress-integrator", channel="edge", revision=103, trust=True),
    )

    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(
            apps=[APP_NAME],
            status="active",
            raise_on_blocked=False,
            timeout=600,
        )
        await ops_test.model.wait_for_idle(
            apps=["nginx-ingress-integrator"],
            status="waiting",
            raise_on_blocked=False,
            timeout=600,
        )

        await ops_test.model.integrate(APP_NAME, "nginx-ingress-integrator")

        await ops_test.model.wait_for_idle(
            apps=[APP_NAME, "nginx-ingress-integrator"],
            status="active",
            raise_on_blocked=False,
            timeout=600,
        )
