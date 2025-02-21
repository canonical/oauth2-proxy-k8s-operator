[![Charmhub Badge](https://charmhub.io/oauth2-proxy-k8s/badge.svg)](https://charmhub.io/oauth2-proxy-k8s)
[![Release Edge](https://github.com/canonical/oauth2-proxy-k8s-operator/actions/workflows/publish_charm.yaml/badge.svg)](https://github.com/canonical/oauth2-proxy-k8s-operator/actions/workflows/publish_charm.yaml)

# OAuth2 Proxy K8s Operator

This is the Kubernetes Python Operator for the
[OAuth2 proxy](https://oauth2-proxy.github.io/oauth2-proxy/).

## Description

OAuth2 Proxy is a reverse proxy and static file server that authenticates users
through providers like Google and GitHub, allowing validation by email, domain,
or group.

This operator provides the OAuth2 proxy, and consists of Python scripts which
wraps the versions distributed by
[OAuth2 proxy](https://quay.io/repository/oauth2-proxy/oauth2-proxy?tab=tags&tag=latest).

## Usage

The OAuth2 Proxy charm can be used to enable authentication for charmed applications
by integrating it with [Identity Platform](https://charmhub.io/identity-platform).

To deploy Charmed OAuth2 Proxy, you need to run the following command:

```shell
juju deploy oauth2-proxy-k8s --channel edge --trust
```

You can follow the deployment status with `watch -c juju status --color`.

## Integrations
<!-- TODO: Update this section when forward-auth and auth-proxy are integrated. -->

### Ingress

The Charmed OAuth2 Proxy offers integration with
the [traefik-k8s-operator](https://github.com/canonical/traefik-k8s-operator)
for ingress.

In order to provide ingress to the application, run:

```shell
juju deploy traefik-k8s --channel latest/stable --trust
juju integrate traefik-k8s oauth2-proxy-k8s:ingress
```

### Identity Platform

Charmed OAuth2 Proxy connects with the Identity Platform with the use of Hydra charmed
operator:

```shell
juju integrate oauth2-proxy-k8s:oauth hydra
```

Identity Platform is a composable identity provider and identity broker system based on Juju.

It comes with a built-in identity and user management system, but is also able to rely on external identity providers
to authenticate users and manage user attributes. Find out more about integrating it with providers like Google, Microsoft Entra ID
or GitHub [here](https://charmhub.io/identity-platform/docs/how-to/integrate-external-identity-provider).

Refer
to [this](https://charmhub.io/topics/canonical-identity-platform/tutorials/e2e-tutorial)
tutorial to learn how to deploy and configure the Identity Platform.

## Security

Security issues can be reported
through [LaunchPad](https://wiki.ubuntu.com/DebuggingSecurity#How%20to%20File).
Please do not file GitHub issues about security issues.

## Contributing

This charm is still in active development. Please see the
[Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and `CONTRIBUTING.md` for developer
guidance.

## License

The Charmed OAuth2 Proxy K8s Operator is free software, distributed under the
Apache Software License, version 2.0. See [License](LICENSE) for more details.
