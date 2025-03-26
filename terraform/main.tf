/**
 * # Terraform Module for OAuth2 Proxy K8s Operator
 *
 * This is a Terraform module facilitating the deployment of the
 * oauth2-proxy-k8s charm using the Juju Terraform provider.
 */

resource "juju_application" "application" {
  name        = var.app_name
  model       = var.model_name
  trust       = true
  config      = var.config
  constraints = var.constraints
  units       = var.units

  charm {
    name     = " oauth2-proxy-k8s"
    base     = var.base
    channel  = var.channel
    revision = var.revision
  }
}
