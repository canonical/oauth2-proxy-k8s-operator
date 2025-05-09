# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Generator
from unittest.mock import MagicMock, create_autospec

import pytest
from ops import Container
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import Oauth2ProxyK8sOperatorCharm


@pytest.fixture()
def harness() -> Generator[Harness, None, None]:
    harness = Harness(Oauth2ProxyK8sOperatorCharm)
    harness.set_model_name("testing")
    harness.set_leader(True)
    harness.begin()
    yield harness
    harness.cleanup()


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture) -> None:
    mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="testing",
        _patch=lambda *a, **kw: True,
        is_ready=lambda *a, **kw: True,
    )


@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


@pytest.fixture()
def mocked_cookie_encryption_key(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.Oauth2ProxyK8sOperatorCharm._cookie_encryption_key",
        return_value="WrfOcYmVBwyduEbKYTUhO4X7XVaOQ1wF",
    )


@pytest.fixture()
def mocked_oauth2_proxy_is_running(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.Oauth2ProxyK8sOperatorCharm._oauth2_proxy_service_is_running", return_value=True
    )


@pytest.fixture
def mocked_forward_auth_update(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charms.oauth2_proxy_k8s.v0.forward_auth.ForwardAuthProvider.update_forward_auth_config"
    )


@pytest.fixture(autouse=True)
def mocked_push_ca_certs(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "integrations.TrustedCertificatesTransferIntegration._push_ca_certs", return_value=None
    )
