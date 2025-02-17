# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import os

import pytest
from lightkube import Client, KubeConfig
from pytest_operator.plugin import OpsTest

KUBECONFIG = os.environ.get("TESTING_KUBECONFIG", "~/.kube/config")


@pytest.fixture(scope="module")
def client() -> Client:
    return Client(config=KubeConfig.from_file(KUBECONFIG))


@pytest.fixture(scope="module")
def lightkube_client(ops_test: OpsTest) -> Client:
    lightkube_client = Client(field_manager="oauth2-proxy-k8s", namespace=ops_test.model.name)
    return lightkube_client
