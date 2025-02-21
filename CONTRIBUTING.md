# Contributing

## Overview

This document explains the processes and practices recommended for contributing
enhancements to this operator.

- Generally, before developing bugs or enhancements to this charm, you
  should [open an issue](https://github.com/canonical/oauth2-proxy-k8s-operator/issues)
  explaining your use case.
- If you would like to chat with us about charm development, you can reach us
  at [Canonical Matrix public channel](https://matrix.to/#/#charmhub-charmdev:ubuntu.com)
  or [Discourse](https://discourse.charmhub.io/).
- Familiarising yourself with the [Charmed Operator Framework](https://juju.is/docs/sdk) library
  will help you a lot when working on new features or bug fixes.
- All enhancements require review before being merged. Code review typically
  examines
  - code quality
  - test coverage
  - user experience for Juju administrators of this charm.
- Please help us out in ensuring easy to review branches by rebasing your pull
  request branch onto the `main` branch. This also avoids merge commits and
  creates a linear Git commit history.

## Developing

You can use the environments created by `tox` for development. It helps
install `pre-commit`, `mypy` type checker, linting tools, and formatting tools.

```shell
tox -e dev
source .tox/dev/bin/activate
```

## Testing

```shell
tox -e lint          # lint checks
tox -e unit          # unit tests
tox -e integration   # integration tests
```

## Building

Build the charm in this git repository using:

```bash
charmcraft pack
```

### Deploying

This charm is used to deploy OAuth2 Proxy in a k8s cluster. For a local
deployment, follow the steps below:

#### Install Microk8s

```bash
# Install Microk8s from snap
sudo snap install microk8s --classic --channel=1.31-strict/stable

# Install charmcraft from snap
sudo snap install charmcraft --classic

# Add the 'ubuntu' user to the Microk8s group
sudo usermod -a -G microk8s ubuntu

# Give the 'ubuntu' user permissions to read the ~/.kube directory
sudo chown -f -R ubuntu ~/.kube

# Create the 'microk8s' group
newgrp microk8s

# Enable the necessary Microk8s addons
microk8s enable hostpath-storage dns
```

#### Set up the Juju OLM

```bash
# Install the Juju CLI client, juju. Minimum version required is juju>=3.1.
sudo snap install juju --classic

# Install a "juju" controller into your "microk8s" cloud
juju bootstrap microk8s test-controller

# Create a 'model' on this controller
juju add-model oauth2-proxy-model

# Enable DEBUG logging
juju model-config logging-config="<root>=INFO;unit=DEBUG"

# Check progress
juju status --relations --watch 2s
juju debug-log
```

#### Deploy Charm

```bash
# Deploy the charm
juju deploy ./*-amd64.charm --resource oauth2-proxy-image=$(yq eval '.resources.oauth2-proxy-image.upstream-source' charmcraft.yaml) --trust

# When making changes, refresh the charm
charmcraft pack && juju refresh --path="./*amd64.charm" oauth2-proxy-k8s --force-units oauth2-proxy-image=$(yq eval '.resources.oauth2-proxy-image.upstream-source' charmcraft.yaml) --trust
```

#### Integrate Charms

```bash
# Deploy traefik operator
juju deploy traefik-k8s --channel latest/stable --trust
juju integrate oauth2-proxy-k8s:ingress traefik-k8s

# Deploy Identity Platform
juju deploy identity-platform --channel latest/edge --trust

# Integrate with oauth
juju integrate oauth2-proxy-k8s:oauth hydra
```

#### Cleanup

```bash
# Clean-up before retrying
# Either remove individual applications
# (The --force flag can optionally be included if any of the units are in error state)
juju remove-application oauth2-proxy-k8s

# Or remove whole model
juju destroy-model oauth2-proxy-model
```

## Canonical Contributor Agreement

Canonical welcomes contributions to Charmed OAuth2 Proxy. Please check out
our [contributor agreement](https://ubuntu.com/legal/contributors) if you're
interested in contributing to the solution.
