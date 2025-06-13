#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for providing OAuth2 Proxy with downstream charms' auth-proxy information.

It is required to integrate a charm into an Identity and Access Proxy (IAP).

## Getting Started

To get started using the library, you need to fetch the library using `charmcraft`.
**Note that you also need to add `jsonschema` to your charm's `requirements.txt`.**

```shell
cd some-charm
charmcraft fetch-lib charms.oauth2_proxy_k8s.v0.auth_proxy
```

To use the library from the requirer side, add the following to the `metadata.yaml` of the charm:

```yaml
requires:
  auth-proxy:
    interface: auth_proxy
    limit: 1
```

Then, to initialise the library:
```python
from charms.oauth2_proxy_k8s.v0.auth_proxy import AuthProxyConfig, AuthProxyRequirer

AUTH_PROXY_ALLOWED_ENDPOINTS = ["welcome", "about/app"]
AUTH_PROXY_HEADERS = ["X-Auth-Request-User", "X-Auth-Request-Email"]
AUTH_PROXY_AUTHENTICATED_EMAILS = ["test@example.com", "test@canonical.com"]
AUTH_PROXY_AUTHENTICATED_EMAIL_DOMAINS = ["canonical.com"]

class SomeCharm(CharmBase):
    def __init__(self, *args):
        # ...
        self.auth_proxy = AuthProxyRequirer(self, self._auth_proxy_config)

        @property
        def external_urls(self) -> list:
            # Get ingress-per-unit or externally-configured web urls
            # ...
            return ["https://example.com/unit-0", "https://example.com/unit-1"]

        @property
        def _auth_proxy_config(self) -> AuthProxyConfig:
            return AuthProxyConfig(
                protected_urls=self.external_urls,
                allowed_endpoints=AUTH_PROXY_ALLOWED_ENDPOINTS,
                headers=AUTH_PROXY_HEADERS,
                authenticated_emails=AUTH_PROXY_AUTHENTICATED_EMAILS,
                authenticated_email_domains=AUTH_PROXY_AUTHENTICATED_EMAIL_DOMAINS
            )

        def _on_ingress_ready(self, event):
            self._configure_auth_proxy()

        def _configure_auth_proxy(self):
            self.auth_proxy.update_auth_proxy_config(auth_proxy_config=self._auth_proxy_config)
```
"""

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Mapping, Optional

import jsonschema
from ops.charm import CharmBase, RelationBrokenEvent, RelationChangedEvent, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Handle, Object, ObjectEvents
from ops.model import Relation, TooManyRelatedAppsError

# The unique Charmhub library identifier, never change it
LIBID = "83df2500c289431aab1567ac1b780926"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 2

RELATION_NAME = "auth-proxy"
INTERFACE_NAME = "auth_proxy"

logger = logging.getLogger(__name__)

ALLOWED_HEADERS = ["X-Auth-Request-User", "X-Auth-Request-Groups", "X-Auth-Request-Email", "X-Auth-Request-Preferred-Username"]

url_regex = re.compile(
    r"(^http://)|(^https://)"  # http:// or https://
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|"
    r"[A-Z0-9-]{2,}\.?)|"  # domain...
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
    r"(?::\d+)?"  # optional port
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

AUTH_PROXY_REQUIRER_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema",
    "$id": "https://canonical.github.io/charm-relation-interfaces/docs/json_schemas/auth_proxy/v0/requirer.json",
    "type": "object",
    "properties": {
        "protected_urls": {"type": "array", "default": None, "items": {"type": "string"}},
        "allowed_endpoints": {"type": "array", "default": [], "items": {"type": "string"}},
        "headers": {
            "type": "array",
            "default": ["X-Auth-Request-User"],
            "items": {
                "enum": ALLOWED_HEADERS,
                "type": "string",
            },
        },
        "authenticated_emails": {"type": "array", "default": [], "items": {"type": "string"}},
        "authenticated_email_domains": {"type": "array", "default": [], "items": {"type": "string"}},
        "app_name": {"type": "string", "default": None},
    },
    "required": ["protected_urls", "allowed_endpoints", "headers", "authenticated_emails", "authenticated_email_domains"],
}


class AuthProxyConfigError(Exception):
    """Emitted when invalid auth proxy config is provided."""


class DataValidationError(RuntimeError):
    """Raised when data validation fails on relation data."""


def _load_data(data: Mapping, schema: Optional[Dict] = None) -> Dict:
    """Parses nested fields and checks whether `data` matches `schema`."""
    ret = {}
    for k, v in data.items():
        try:
            ret[k] = json.loads(v)
        except json.JSONDecodeError:
            ret[k] = v

    if schema:
        _validate_data(ret, schema)
    return ret


def _dump_data(data: Dict, schema: Optional[Dict] = None) -> Dict:
    if schema:
        _validate_data(data, schema)

    ret = {}
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            try:
                ret[k] = json.dumps(v)
            except json.JSONDecodeError as e:
                raise DataValidationError(f"Failed to encode relation json: {e}")
        else:
            ret[k] = v
    return ret


class AuthProxyRelation(Object):
    """A class containing helper methods for auth-proxy relation."""

    def _pop_relation_data(self, relation_id: Relation) -> None:
        if not self.model.unit.is_leader():
            return

        if not self._charm.model.relations[self._relation_name]:
            return

        relation = self.model.get_relation(self._relation_name, relation_id=relation_id)
        if not relation or not relation.app:
            return

        try:
            for data in list(relation.data[self.model.app]):
                relation.data[self.model.app].pop(data, "")
        except Exception as e:
            logger.info("Failed to pop the relation data: %s", e)


def _validate_data(data: Dict, schema: Dict) -> None:
    """Checks whether `data` matches `schema`.

    Will raise DataValidationError if the data is not valid, else return None.
    """
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        raise DataValidationError(data, schema) from e


@dataclass
class AuthProxyConfig:
    """Helper class containing a configuration for the charm related with OAuth2 Proxy."""

    protected_urls: List[str]
    headers: List[str] = field(default_factory=lambda: [])
    allowed_endpoints: List[str] = field(default_factory=lambda: [])
    authenticated_emails: List[str] = field(default_factory=lambda: [])
    authenticated_email_domains: List[str] = field(default_factory=lambda: [])
    app_name: Optional[str] = None

    def validate(self) -> None:
        """Validate the auth proxy configuration."""
        # Validate protected_urls
        for url in self.protected_urls:
            if not re.match(url_regex, url):
                raise AuthProxyConfigError(f"Invalid URL {url}")

        for url in self.protected_urls:
            if url.startswith("http://"):
                logger.warning("Provided URL %s uses http scheme. Don't do this in production", url)

        # Validate headers
        for header in self.headers:
            if header not in ALLOWED_HEADERS:
                raise AuthProxyConfigError(
                    f"Unsupported header {header}, it must be one of {ALLOWED_HEADERS}"
                )

    def to_dict(self) -> Dict:
        """Convert object to dict."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class AuthProxyConfigChangedEvent(EventBase):
    """Event to notify the Provider charm that the auth proxy config has changed."""

    def __init__(
        self,
        handle: Handle,
        protected_urls: List[str],
        headers: List[str],
        allowed_endpoints: List[str],
        authenticated_emails: List[str],
        authenticated_email_domains: List[str],
        relation_id: int,
        relation_app_name: str,
    ) -> None:
        super().__init__(handle)
        self.protected_urls = protected_urls
        self.allowed_endpoints = allowed_endpoints
        self.headers = headers
        self.authenticated_emails = authenticated_emails
        self.authenticated_email_domains = authenticated_email_domains
        self.relation_id = relation_id
        self.relation_app_name = relation_app_name

    def snapshot(self) -> Dict:
        """Save event."""
        return {
            "protected_urls": self.protected_urls,
            "headers": self.headers,
            "allowed_endpoints": self.allowed_endpoints,
            "authenticated_emails": self.authenticated_emails,
            "authenticated_email_domains": self.authenticated_email_domains,
            "relation_id": self.relation_id,
            "relation_app_name": self.relation_app_name,
        }

    def restore(self, snapshot: Dict) -> None:
        """Restore event."""
        self.protected_urls = snapshot["protected_urls"]
        self.headers = snapshot["headers"]
        self.allowed_endpoints = snapshot["allowed_endpoints"]
        self.authenticated_emails = snapshot["authenticated_emails"]
        self.authenticated_email_domains = snapshot["authenticated_email_domains"]
        self.relation_id = snapshot["relation_id"]
        self.relation_app_name = snapshot["relation_app_name"]

    def to_auth_proxy_config(self) -> AuthProxyConfig:
        """Convert the event information to an AuthProxyConfig object."""
        return AuthProxyConfig(
            self.protected_urls,
            self.allowed_endpoints,
            self.headers,
            self.authenticated_emails,
            self.authenticated_email_domains,
        )


class AuthProxyConfigRemovedEvent(EventBase):
    """Event to notify the provider charm that the auth proxy config was removed."""

    def __init__(
        self,
        handle: Handle,
        relation_id: int,
    ) -> None:
        super().__init__(handle)
        self.relation_id = relation_id

    def snapshot(self) -> Dict:
        """Save event."""
        return {"relation_id": self.relation_id}

    def restore(self, snapshot: Dict) -> None:
        """Restore event."""
        self.relation_id = snapshot["relation_id"]


class AuthProxyProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `AuthProxyProvider`."""

    proxy_config_changed = EventSource(AuthProxyConfigChangedEvent)
    config_removed = EventSource(AuthProxyConfigRemovedEvent)


class AuthProxyProvider(AuthProxyRelation):
    """Provider side of the auth-proxy relation."""

    on = AuthProxyProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME) -> None:
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_relation_changed_event)
        self.framework.observe(events.relation_broken, self._on_relation_broken_event)

    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        """Get the auth-proxy config and emit a custom config-changed event."""
        if not self.model.unit.is_leader():
            return

        data = event.relation.data[event.app]
        if not data:
            logger.info("No requirer relation data available.")
            return

        try:
            auth_proxy_data = _load_data(data, AUTH_PROXY_REQUIRER_JSON_SCHEMA)
        except DataValidationError as e:
            logger.error(
                "Received invalid config from the requirer: %s. Config-changed will not be emitted", e
            )
            return

        protected_urls = auth_proxy_data.get("protected_urls")
        allowed_endpoints = auth_proxy_data.get("allowed_endpoints")
        headers = auth_proxy_data.get("headers")
        authenticated_emails = auth_proxy_data.get("authenticated_emails")
        authenticated_email_domains = auth_proxy_data.get("authenticated_email_domains")

        relation_id = event.relation.id
        relation_app_name = event.relation.app.name

        # Notify OAuth2 Proxy to reconfigure
        self.on.proxy_config_changed.emit(
            protected_urls, headers, allowed_endpoints, authenticated_emails, authenticated_email_domains, relation_id, relation_app_name
        )

    def _on_relation_broken_event(self, event: RelationBrokenEvent) -> None:
        """Wipe the relation databag and notify OAuth2 Proxy that the relation is broken."""
        # Workaround for https://github.com/canonical/operator/issues/888
        self._pop_relation_data(event.relation.id)

        self.on.config_removed.emit(event.relation.id)

    def get_app_names(self) -> List[str]:
        """Returns the list of all related app names."""
        if not self._charm.model.relations[self._relation_name]:
            return []

        app_names = []
        for relation in self._charm.model.relations[self._relation_name]:
            if relation.data[relation.app]:
                app_names.append(relation.data[relation.app]["app_name"])

        return app_names

    def get_relations_data(self, key: str) -> Optional[List[str]]:
        """Returns a list of key values from all auth-proxy relations."""
        if not self._charm.model.relations[self._relation_name]:
            return None

        relations_data = set()
        for relation in self._charm.model.relations[self._relation_name]:
            if relation.data[relation.app]:
                if values := json.loads(relation.data[relation.app][key]):
                    for v in values:
                        relations_data.add(v)
                else:
                    return None

        return list(relations_data)


class InvalidAuthProxyConfigEvent(EventBase):
    """Event to notify the charm that the auth proxy configuration is invalid."""

    def __init__(self, handle: Handle, error: str) -> None:
        super().__init__(handle)
        self.error = error

    def snapshot(self) -> Dict:
        """Save event."""
        return {
            "error": self.error,
        }

    def restore(self, snapshot: Dict) -> None:
        """Restore event."""
        self.error = snapshot["error"]


class AuthProxyRelationRemovedEvent(EventBase):
    """Custom event to notify the charm that the relation was removed."""

    def snapshot(self) -> Dict:
        """Save event."""
        return {}

    def restore(self, snapshot: Dict) -> None:
        """Restore event."""
        pass


class AuthProxyRequirerEvents(ObjectEvents):
    """Event descriptor for events raised by `AuthProxyRequirer`."""

    invalid_auth_proxy_config = EventSource(InvalidAuthProxyConfigEvent)
    auth_proxy_relation_removed = EventSource(AuthProxyRelationRemovedEvent)


class AuthProxyRequirer(AuthProxyRelation):
    """Requirer side of the auth-proxy relation."""

    on = AuthProxyRequirerEvents()

    def __init__(
        self,
        charm: CharmBase,
        auth_proxy_config: Optional[AuthProxyConfig] = None,
        relation_name: str = RELATION_NAME,
    ) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        self._auth_proxy_config = auth_proxy_config

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_created_event)
        self.framework.observe(events.relation_broken, self._on_relation_broken_event)

    def _on_relation_created_event(self, event: RelationCreatedEvent) -> None:
        """Update the relation with auth proxy config when a relation is created."""
        if not self.model.unit.is_leader():
            return

        try:
            self._update_relation_data(self._auth_proxy_config, event.relation.id)
        except AuthProxyConfigError as e:
            self.on.invalid_auth_proxy_config.emit(e.args[0])

    def _on_relation_broken_event(self, event: RelationBrokenEvent) -> None:
        """Wipe the relation databag and notify the charm when the relation is broken."""
        # Workaround for https://github.com/canonical/operator/issues/888
        self._pop_relation_data(event.relation.id)

        self.on.auth_proxy_relation_removed.emit()

    def _update_relation_data(
        self, auth_proxy_config: Optional[AuthProxyConfig], relation_id: Optional[int] = None
    ) -> None:
        """Validate the auth-proxy config and update the relation databag."""
        if not self.model.unit.is_leader():
            return

        if not auth_proxy_config:
            logger.info("Auth proxy config is missing")
            return

        if not isinstance(auth_proxy_config, AuthProxyConfig):
            raise ValueError(f"Unexpected auth_proxy_config type: {type(auth_proxy_config)}")

        auth_proxy_config.validate()

        try:
            relation = self.model.get_relation(
                relation_name=self._relation_name, relation_id=relation_id
            )
        except TooManyRelatedAppsError:
            raise RuntimeError("More than one relations are defined. Please provide a relation_id")

        if not relation or not relation.app:
            return

        data = _dump_data(auth_proxy_config.to_dict(), AUTH_PROXY_REQUIRER_JSON_SCHEMA)
        data["app_name"] = self._charm.app.name
        relation.data[self.model.app].update(data)

    def update_auth_proxy_config(
        self, auth_proxy_config: AuthProxyConfig, relation_id: Optional[int] = None
    ) -> None:
        """Update the auth proxy config stored in the object."""
        self._update_relation_data(auth_proxy_config, relation_id=relation_id)
