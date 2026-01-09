# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import secrets
import shutil
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Generator

import jubilant
import pytest
from lightkube import Client, KubeConfig

from tests.integration.constants import AUTH_PROXY_REQUIRER, KUBECONFIG
from tests.integration.utils import juju_model_factory


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options for model management and deployment control.

    This function adds the following options:
        --keep-models, --no-teardown: Keep the Juju model after the test is finished.
        --model: Specify the Juju model to run the tests on.
        --no-deploy, --no-setup: Skip deployment of the charm.
    """
    parser.addoption(
        "--keep-models",
        "--no-teardown",
        action="store_true",
        dest="no_teardown",
        default=False,
        help="Keep the model after the test is finished.",
    )
    parser.addoption(
        "--model",
        action="store",
        dest="model",
        default=None,
        help="The model to run the tests on.",
    )
    parser.addoption(
        "--no-deploy",
        "--no-setup",
        action="store_true",
        dest="no_setup",
        default=False,
        help="Skip deployment of the charm.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for test selection based on deployment and model management.

    This function registers the following markers:
        setup: Skip tests if the charm is already deployed.
        teardown: Skip tests if the no_teardown option is set.
    """
    config.addinivalue_line("markers", "setup: tests that setup some parts of the environment")
    config.addinivalue_line(
        "markers", "teardown: tests that teardown some parts of the environment."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Modify collected test items based on command-line options.

    This function skips tests with specific markers based on the provided command-line options:
        - If no_setup is set, tests marked with "no_setup
          are skipped.
        - If no_teardown is set, tests marked with "no_teardown"
          are skipped.
    """
    skip_setup = pytest.mark.skip(reason="no_setup provided")
    skip_teardown = pytest.mark.skip(reason="no_teardown provided")
    for item in items:
        if config.getoption("no_setup") and "setup" in item.keywords:
            item.add_marker(skip_setup)
        if config.getoption("no_teardown") and "teardown" in item.keywords:
            item.add_marker(skip_teardown)


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    """Create a temporary Juju model for integration tests."""
    model_name = request.config.getoption("--model")
    if not model_name:
        model_name = f"test-oauth2-proxy-{secrets.token_hex(4)}"

    juju_ = juju_model_factory(model_name)
    juju_.wait_timeout = 10 * 60

    try:
        yield juju_
    finally:
        if request.session.testsfailed:
            log = juju_.debug_log(limit=1000)
            print(log, end="")

        no_teardown = bool(request.config.getoption("--no-teardown"))
        keep_model = no_teardown or request.session.testsfailed > 0
        if not keep_model:
            with suppress(jubilant.CLIError):
                args = [
                    "destroy-model",
                    juju_.model,
                    "--no-prompt",
                    "--destroy-storage",
                    "--force",
                    "--timeout",
                    "10m",
                ]
                juju_.cli(*args)


@pytest.fixture(scope="module")
def client() -> Client:
    return Client(config=KubeConfig.from_file(KUBECONFIG))


@pytest.fixture(scope="module")
def lightkube_client(juju: jubilant.Juju) -> Client:
    lightkube_client = Client(field_manager="oauth2-proxy-k8s", namespace=juju.model)
    return lightkube_client


@pytest.fixture(autouse=True, scope="module")
def copy_libraries_into_tester_charm() -> None:
    """Ensure the tester charm has the required libraries."""
    libraries = [
        "traefik_k8s/v2/ingress.py",
        "oauth2_proxy_k8s/v0/auth_proxy.py",
    ]

    for lib in libraries:
        install_path = f"tests/integration/{AUTH_PROXY_REQUIRER}/lib/charms/{lib}"
        os.makedirs(os.path.dirname(install_path), exist_ok=True)
        shutil.copyfile(f"lib/charms/{lib}", install_path)


def build_charm_artifact(charm_dir: Path) -> Path:
    """Helper to build a charm and return its path."""
    subprocess.run(["charmcraft", "pack"], cwd=charm_dir, check=True)

    charms = list(charm_dir.glob("*.charm"))
    if charms:
        return charms[0].absolute()
    else:
        raise RuntimeError(f"Charm not found and build failed in {charm_dir}")


@pytest.fixture(scope="module")
def local_charm() -> Path:
    # Look for pre-built charm
    if charm := os.getenv("CHARM_PATH"):
        return Path(charm)

    # Fallback to local build
    return build_charm_artifact(Path("."))


@pytest.fixture(scope="module")
def requirer_charm() -> Path:
    return build_charm_artifact(Path(f"tests/integration/{AUTH_PROXY_REQUIRER}"))
