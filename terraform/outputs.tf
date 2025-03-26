# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "The Juju application name"
  value       = juju_application.application.name
}

output "requires" {
  description = "The Juju integrations that the charm requires"
  value = {
    ingress         = "ingress"
    oauth           = "oauth"
    receive-ca-cert = "receive-ca-cert"
  }
}

output "provides" {
  description = "The Juju integrations that the charm provides"
  value = {
    auth-proxy   = "auth-proxy"
    forward-auth = "forward-auth"
  }
}
