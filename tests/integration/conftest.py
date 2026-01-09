# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Iterator

import jubilant
import pytest
from lightkube import Client, KubeConfig

from tests.integration.constants import AUTH_PROXY_REQUIRER, KUBECONFIG
from tests.integration.utils import create_temp_juju_model


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options for model management and deployment control.

    This function adds the following options:
        --keep-models: Keep the Juju model after the test is finished.
        --model: Specify the Juju model to run the tests on.
        --no-deploy: Skip deployment of the charm.
    """
    parser.addoption(
        "--keep-models",
        action="store_true",
        default=False,
        help="Keep the model after the test is finished.",
    )
    parser.addoption(
        "--model",
        action="store",
        default=None,
        help="The model to run the tests on.",
    )
    parser.addoption(
        "--no-deploy",
        action="store_true",
        default=False,
        help="Skip deployment of the charm.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for test selection based on deployment and model management.

    This function registers the following markers:
        skip_if_deployed: Skip tests if the charm is already deployed.
        skip_if_keep_models: Skip tests if the --keep-models option is set.
    """
    config.addinivalue_line("markers", "skip_if_deployed: skip test if deployed")
    config.addinivalue_line("markers", "skip_if_keep_models: skip test if --keep-models is set.")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Modify collected test items based on command-line options.

    This function skips tests with specific markers based on the provided command-line options:
        - If --no-deploy is set, tests marked with "skip_if_deployed
          are skipped.
        - If --keep-models is set, tests marked with "skip_if_keep_models"
          are skipped.
    """
    for item in items:
        if config.getoption("--no-deploy") and "skip_if_deployed" in item.keywords:
            skip_deployed = pytest.mark.skip(reason="skipping deployment")
            item.add_marker(skip_deployed)
        if config.getoption("--keep-models") and "skip_if_keep_models" in item.keywords:
            skip_keep_models = pytest.mark.skip(
                reason="skipping test because --keep-models is set"
            )
            item.add_marker(skip_keep_models)


@pytest.fixture(scope="module")
def model(request: pytest.FixtureRequest) -> Iterator[jubilant.Juju]:
    """Create a temporary Juju model for integration tests."""
    model_name = request.config.getoption("--model")
    if not model_name:
        model_name = f"test-oauth2-proxy-{uuid.uuid4().hex[-8:]}"

    yield from create_temp_juju_model(request, model=model_name)


@pytest.fixture(scope="module")
def client() -> Client:
    return Client(config=KubeConfig.from_file(KUBECONFIG))


@pytest.fixture(scope="module")
def lightkube_client(model: jubilant.Juju) -> Client:
    lightkube_client = Client(field_manager="oauth2-proxy-k8s", namespace=model.model)
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
def local_charm():
    # Look for pre-built charm
    if charm := os.getenv("CHARM_PATH"):
        return Path(charm)

    # Fallback to local build
    return build_charm_artifact(Path("."))


@pytest.fixture(scope="module")
def requirer_charm():
    return build_charm_artifact(Path(f"tests/integration/{AUTH_PROXY_REQUIRER}"))
