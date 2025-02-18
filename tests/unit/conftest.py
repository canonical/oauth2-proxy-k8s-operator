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


@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


@pytest.fixture()
def mocked_cookie_encryption_key(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.Oauth2ProxyK8sOperatorCharm._cookie_encryption_key", return_value="WrfOcYmVBwyduEbKYTUhO4X7XVaOQ1wF")
