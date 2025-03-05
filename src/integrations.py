# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from dataclasses import dataclass, field
from typing import List

from charms.oauth2_proxy_k8s.v0.auth_proxy import AuthProxyProvider


@dataclass(frozen=True, slots=True)
class AuthProxyIntegrationData:
    """Data source from the auth-proxy integration."""

    app_names: List[str] = field(default_factory=list)
    allowed_endpoints: List[str] = field(default_factory=list)
    headers: List[str] = field(default_factory=list)
    authenticated_emails: List[str] = field(default_factory=list)
    authenticated_email_domains: List[str] = field(default_factory=list)

    @classmethod
    def load(cls, provider: AuthProxyProvider) -> "AuthProxyIntegrationData":
        app_names = provider.get_app_names()
        allowed_endpoints = provider.get_relations_data("allowed_endpoints")
        headers = provider.get_relations_data("headers")
        authenticated_emails = provider.get_relations_data("authenticated_emails")
        authenticated_email_domains = provider.get_relations_data("authenticated_email_domains")

        return cls(
            app_names=app_names,
            allowed_endpoints=allowed_endpoints,
            headers=headers,
            authenticated_emails=authenticated_emails,
            authenticated_email_domains=authenticated_email_domains,
        )
