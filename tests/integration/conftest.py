# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import shutil

import pytest
from lightkube import Client, KubeConfig
from pytest_operator.plugin import OpsTest

KUBECONFIG = os.environ.get("TESTING_KUBECONFIG", "~/.kube/config")
AUTH_PROXY_REQUIRER = "auth-proxy-requirer"


@pytest.fixture(scope="module")
def client() -> Client:
    return Client(config=KubeConfig.from_file(KUBECONFIG))


@pytest.fixture(scope="module")
def lightkube_client(ops_test: OpsTest) -> Client:
    lightkube_client = Client(field_manager="oauth2-proxy-k8s", namespace=ops_test.model.name)
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
