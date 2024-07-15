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

The OAuth2 Proxy charm can be used to enable authentication for charmed and
non-charmed applications, by providing the oauth2 configuration to the charm,
and setting the `upstream` config value to the name of your application's k8s
service. For charmed applications, this is the name of the deployed application.

### Enable TLS

To enable TLS connections, you must have a TLS certificate stored as a k8s
secret (default name is oauth2-proxy-tls”). The secret name can be configured
using the `tls-secret-name` config property in the charm. A self-signed
certificate for development purposes can be created as follows:

```bash
# Generate private key
openssl genrsa -out server.key 2048

# Generate a certificate signing request
openssl req -new -key server.key -out server.csr -subj "/CN=oauth2-proxy-k8s"

# Create self-signed certificate
openssl x509 -req -days 365 -in server.csr -signkey server.key -out server.crt -extfile <(printf "subjectAltName=DNS:oauth2-proxy-k8s")

# Create a k8s secret
kubectl -n <model-name> create secret tls oauth2-proxy-tls --cert=server.crt --key=server.key
```

### Deploy

To deploy Charmed OAuth2 Proxy, you need to run the following commands, which
will enable ingress in your microk8s, fetch the charm from
[Charmhub](https://charmhub.io/nginx-ingress-integrator) and deploy it to your
model. By default, the application is configured to use Google OAuth as the
authentication provider. A Google Cloud project can be set up using the
instructions found
[here](https://support.google.com/cloud/answer/6158849?hl=en). The provider can
be changed using the `provider` config.

```bash
# Deploy ingress controller.
sudo microk8s enable ingress:default-ssl-certificate=<model-name>/oauth2-proxy-tls

# Deploy charms
juju deploy oauth2-proxy-k8s --channel edge
juju deploy nginx-ingress-integrator --channel edge --revision 103 --trust

# Set the necessary config (example below for Google OAuth)
juju config oauth2-proxy-k8s \
                upstream=<requirer_application_name> \
                client-id=<client_id> \
                client-secret=<client_secret> \
                cookie-secret=<cookie_secret>

# Relate the charms
juju relate oauth2-proxy-k8s nginx-ingress-integrator
```

### Verify Ingress Resource

To verify the ingress resources were correctly created, you can run the
following command:

```bash
kubectl describe ingress -n <model-name>
```

### Connect Ingress

Once deployed and related, find the IP of the ingress controller by running the
following command:

```bash
kubectl get pods -n ingress -o wide
```

You should see something similar to the following output:

```
NAME                                      READY   STATUS    RESTARTS          AGE    IP           NODE      NOMINATED NODE   READINESS GATES
nginx-ingress-microk8s-controller-mfmtx   1/1     Running   512 (3h15m ago)   145d   10.1.232.8   ubuntu   <none>           <none>
```

Take note of the ingress controller IP address and add the IP-to-hostname
mapping in your `/etc/hosts` file as follows:

```bash
sudo nano /etc/hosts

# Add the following entries
10.1.232.8     oauth2-proxy-k8s
```

By default, the hostname will be set to the application name `oauth2-proxy-k8s`.
You should now be able to access your application at this address.

## Verifying

To verify that the setup is running correctly, run
`juju status --relations --watch 2s` and ensure that all pods are active and the
required integrations exist.

## Contributing

This charm is still in active development. Please see the
[Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and `CONTRIBUTING.md` for developer
guidance.

## License

The Charmed OAuth2 Proxy K8s Operator is free software, distributed under the
Apache Software License, version 2.0. See [License](LICENSE) for more details.
