"""One verifying :class:`ssl.SSLContext` for every HTTPS request the toolbox makes.

The SimNIBS container ships a conda-built Python whose OpenSSL still carries the build-time
placeholder CA paths (``.../_h_env_placehold_placehold.../ssl/cert.pem``), so
:func:`ssl.create_default_context` there trusts nothing and every ``urllib`` call dies with
``CERTIFICATE_VERIFY_FAILED``. :func:`ssl_context` fixes that by naming a bundle explicitly:

1. ``SSL_CERT_FILE`` / ``REQUESTS_CA_BUNDLE`` -- the escape hatch for a TLS-inspecting proxy;
2. :mod:`certifi`, which the SimNIBS environment already has;
3. a well-known system bundle (``/etc/ssl/certs/ca-certificates.crt`` and friends);
4. the interpreter default, for hosts where it works.

Verification is never disabled -- no ``CERT_NONE``, no ``check_hostname = False``, not behind a
flag. When no bundle can be found the request fails and :func:`ca_bundle_hint` says what to set.
"""

from __future__ import annotations

import os
import ssl
from pathlib import Path

__all__ = ["CA_BUNDLE_ENV_VARS", "ca_bundle_hint", "ssl_context"]

#: Environment variables a user behind a TLS-inspecting proxy can point at their own bundle.
CA_BUNDLE_ENV_VARS = ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")

#: Distribution CA bundles, tried when :mod:`certifi` is unavailable.
_SYSTEM_CA_BUNDLES = (
    "/etc/ssl/certs/ca-certificates.crt",  # Debian / Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",  # RHEL / CentOS / Fedora
    "/etc/ssl/cert.pem",  # Alpine / macOS
    "/etc/ssl/ca-bundle.pem",  # openSUSE
)


def _certifi_bundle() -> str | None:
    try:
        import certifi
    except ImportError:
        return None
    where = certifi.where()
    return where if Path(where).is_file() else None


def ca_bundle() -> str | None:
    """The CA bundle to verify against, or ``None`` to fall back to the interpreter default."""
    for var in CA_BUNDLE_ENV_VARS:
        configured = os.environ.get(var, "").strip()
        if configured and Path(configured).is_file():
            return configured
    bundle = _certifi_bundle()
    if bundle:
        return bundle
    for candidate in _SYSTEM_CA_BUNDLES:
        if Path(candidate).is_file():
            return candidate
    return None


def ssl_context() -> ssl.SSLContext:
    """A **verifying** context: hostname checking on, ``CERT_REQUIRED``, best bundle available."""
    bundle = ca_bundle()
    context = ssl.create_default_context(cafile=bundle) if bundle else ssl.create_default_context()
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def ca_bundle_hint() -> str:
    """One line to append to a TLS failure, telling the user how to supply their own bundle."""
    return (
        "TLS certificate verification failed. If you are behind a proxy that inspects TLS, "
        "point SSL_CERT_FILE (or REQUESTS_CA_BUNDLE) at your organisation's CA bundle."
    )
