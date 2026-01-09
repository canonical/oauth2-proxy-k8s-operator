# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import os
from pathlib import Path

import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
APP_NAME = METADATA["name"]
IMAGE_PATH = METADATA["resources"]["oauth2-proxy-image"]["upstream-source"]
TRAEFIK = "traefik-k8s"
CERTIFICATES_PROVIDER = "self-signed-certificates"
AUTH_PROXY_REQUIRER = "auth-proxy-requirer"
KUBECONFIG = os.environ.get("TESTING_KUBECONFIG", "~/.kube/config")
