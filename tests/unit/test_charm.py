# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing


"""Charm unit tests."""

# pylint:disable=protected-access

from unittest import TestCase, mock

from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import CheckStatus
from ops.testing import Harness

from charm import Oauth2ProxyK8SOperatorCharm
from src.charm import HTTP_PORT

APP_NAME = "oauth2-proxy"
mock_incomplete_pebble_plan = {"services": {"oauth2-proxy": {"override": "replace"}}}
BASE_CONFIG = {
    "upstream": "upstream",
    "provider": "google",
    "client-id": "client-id",
    "client-secret": "client-secret",
    "cookie-secret": "cookie-secret",
}


class TestCharm(TestCase):
    """Unit tests for charm.

    Attrs:
        maxDiff: Specifies max difference shown by failed tests.
    """

    maxDiff = None

    def setUp(self):
        """Create setup for the unit tests."""
        self.harness = Harness(Oauth2ProxyK8SOperatorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_can_connect(APP_NAME, True)
        self.harness.set_leader(True)
        self.harness.set_model_name("oauth2-proxy-model")
        self.harness.begin()

    def test_initial_plan(self):
        """The initial pebble plan is empty."""
        initial_plan = self.harness.get_container_pebble_plan(APP_NAME).to_dict()
        self.assertEqual(initial_plan, {})

    def test_blocked_by_missing_config(self):
        """The charm is blocked without a peer relation."""
        harness = self.harness

        # Simulate pebble readiness.
        container = harness.model.unit.get_container(APP_NAME)
        harness.charm.on[APP_NAME].pebble_ready.emit(container)

        # No plans are set yet.
        got_plan = harness.get_container_pebble_plan(APP_NAME).to_dict()
        self.assertEqual(got_plan, {})

        # The BlockStatus is set with a message.
        self.assertEqual(harness.model.unit.status, BlockedStatus("missing `upstream` config"))

        harness.update_config({"upstream": "upstream"})
        self.assertEqual(harness.model.unit.status, BlockedStatus("missing `cookie-secret` config"))

        harness.update_config({"cookie-secret": "cookie-secret"})
        self.assertEqual(
            harness.model.unit.status,
            BlockedStatus("`client-id` and `client-secret` config must be set for `google` provider"),
        )

        harness.update_config({"client-id": "client-id", "client-secret": "client-secret"})
        self.assertEqual(
            harness.model.unit.status,
            MaintenanceStatus("replanning application"),
        )

    def test_ingress(self):
        """The charm relates correctly to the nginx ingress charm and can be configured."""
        harness = self.harness

        simulate_lifecycle(harness)

        nginx_route_relation_id = harness.add_relation("nginx-route", "ingress")
        harness.charm._require_nginx_route()

        assert harness.get_relation_data(nginx_route_relation_id, harness.charm.app) == {
            "service-namespace": harness.charm.model.name,
            "service-hostname": harness.charm.app.name,
            "service-name": harness.charm.app.name,
            "service-port": str(HTTP_PORT),
            "tls-secret-name": "oauth2-proxy-tls",
            "backend-protocol": "HTTP",
        }

    def test_ingress_update_hostname(self):
        """The charm relates correctly to the nginx ingress charm and can be configured."""
        harness = self.harness

        simulate_lifecycle(harness)

        nginx_route_relation_id = harness.add_relation("nginx-route", "ingress")

        new_hostname = "new-oauth2-proxy-k8s"
        harness.update_config({"external-hostname": new_hostname})
        harness.charm._require_nginx_route()

        assert harness.get_relation_data(nginx_route_relation_id, harness.charm.app) == {
            "service-namespace": harness.charm.model.name,
            "service-hostname": new_hostname,
            "service-name": harness.charm.app.name,
            "service-port": str(HTTP_PORT),
            "tls-secret-name": "oauth2-proxy-tls",
            "backend-protocol": "HTTP",
        }

    def test_ingress_update_tls(self):
        """The charm relates correctly to the nginx ingress charm and can be configured."""
        harness = self.harness

        simulate_lifecycle(harness)

        nginx_route_relation_id = harness.add_relation("nginx-route", "ingress")

        new_tls = "new-tls"
        harness.update_config({"tls-secret-name": new_tls})
        harness.charm._require_nginx_route()

        assert harness.get_relation_data(nginx_route_relation_id, harness.charm.app) == {
            "service-namespace": harness.charm.model.name,
            "service-hostname": harness.charm.app.name,
            "service-name": harness.charm.app.name,
            "service-port": str(HTTP_PORT),
            "tls-secret-name": new_tls,
            "backend-protocol": "HTTP",
        }

    def test_ready(self):
        """The pebble plan is correctly generated when the charm is ready."""
        harness = self.harness

        simulate_lifecycle(harness)

        # The plan is generated after pebble is ready.
        want_plan = {
            "services": {
                APP_NAME: {
                    "summary": APP_NAME,
                    "command": "/bin/oauth2-proxy --http-address=0.0.0.0:80 --upstream=upstream --provider=google --client-id=client-id --client-secret=client-secret --cookie-secret=cookie-secret --email-domain=*",
                    "startup": "enabled",
                    "override": "replace",
                    "on-check-failure": {"up": "ignore"},
                }
            },
            "checks": {
                "up": {
                    "override": "replace",
                    "period": "10s",
                    "http": {"url": f"http://localhost:{HTTP_PORT}/ready"},
                }
            },
        }

        got_plan = harness.get_container_pebble_plan(APP_NAME).to_dict()
        self.assertEqual(got_plan, want_plan)

        # The service was started.
        service = harness.model.unit.get_container(APP_NAME).get_service(APP_NAME)
        self.assertTrue(service.is_running())

    def test_update_status_up(self):
        """The charm updates the unit status to active based on UP status."""
        harness = self.harness

        simulate_lifecycle(harness)

        container = harness.model.unit.get_container(APP_NAME)
        container.get_check = mock.Mock(status="up")
        container.get_check.return_value.status = CheckStatus.UP
        harness.charm.on.update_status.emit()

        self.assertEqual(harness.model.unit.status, ActiveStatus())

    def test_update_status_down(self):
        """The charm updates the unit status to maintenance based on DOWN status."""
        harness = self.harness

        simulate_lifecycle(harness)

        container = harness.model.unit.get_container(APP_NAME)
        container.get_check = mock.Mock(status="up")
        container.get_check.return_value.status = CheckStatus.DOWN
        harness.charm.on.update_status.emit()

        self.assertEqual(harness.model.unit.status, MaintenanceStatus("Status check: DOWN"))

    def test_incomplete_pebble_plan(self):
        """The charm re-applies the pebble plan if incomplete."""
        harness = self.harness
        simulate_lifecycle(harness)

        container = harness.model.unit.get_container(APP_NAME)
        container.add_layer(APP_NAME, mock_incomplete_pebble_plan, combine=True)
        harness.charm.on.update_status.emit()

        self.assertEqual(
            harness.model.unit.status,
            MaintenanceStatus("replanning application"),
        )
        plan = harness.get_container_pebble_plan(APP_NAME).to_dict()
        assert plan != mock_incomplete_pebble_plan

    @mock.patch("charm.Oauth2ProxyK8SOperatorCharm._validate_pebble_plan", return_value=True)
    def test_missing_pebble_plan(self, mock_validate_pebble_plan):
        """The charm re-applies the pebble plan if missing."""
        harness = self.harness
        simulate_lifecycle(harness)

        mock_validate_pebble_plan.return_value = False
        harness.charm.on.update_status.emit()
        self.assertEqual(
            harness.model.unit.status,
            MaintenanceStatus("replanning application"),
        )
        plan = harness.get_container_pebble_plan(APP_NAME).to_dict()
        assert plan is not None


def simulate_lifecycle(harness):
    """Simulate a healthy charm life-cycle.

    Args:
        harness: ops.testing.Harness object used to simulate charm lifecycle.
    """
    # Simulate pebble readiness.
    container = harness.model.unit.get_container(APP_NAME)
    harness.charm.on[APP_NAME].pebble_ready.emit(container)

    harness.update_config(BASE_CONFIG)
