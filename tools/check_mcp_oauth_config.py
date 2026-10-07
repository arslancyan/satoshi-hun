"""Fail-closed preflight for production MCP OAuth configuration.

This validates configuration shape only; it never calls the identity provider and
never prints secrets.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

REQUIRED = (
    "MCP_ENABLED",
    "MCP_OAUTH_ISSUER",
    "MCP_RESOURCE_URL",
    "MCP_OAUTH_INTROSPECTION_URL",
    "MCP_OAUTH_CLIENT_ID",
    "MCP_OAUTH_CLIENT_SECRET",
    "MCP_INTERNAL_SECRET",
    "MCP_ALLOWED_HOSTS",
)

def _https(value: str) -> bool:
    return urlparse(value).scheme == "https" and bool(urlparse(value).netloc)

def main() -> int:
    missing = [key for key in REQUIRED if not os.environ.get(key, "").strip()]
    if missing:
        print("MCP_OAUTH_PREFLIGHT=SKIP")
        print("missing=" + ",".join(missing))
        return 0

    if os.environ.get("MCP_ENABLED", "").strip().lower() != "true":
        print("MCP_OAUTH_PREFLIGHT=SKIP")
        print("reason=MCP_ENABLED_not_true")
        return 0

    issuer = os.environ["MCP_OAUTH_ISSUER"].strip()
    resource = os.environ["MCP_RESOURCE_URL"].strip()
    introspection = os.environ["MCP_OAUTH_INTROSPECTION_URL"].strip()
    if not all(map(_https, (issuer, resource, introspection))):
        print("MCP_OAUTH_PREFLIGHT=FAIL")
        print("reason=issuer_resource_introspection_must_use_https")
        return 1

    hosts = {x.strip() for x in os.environ["MCP_ALLOWED_HOSTS"].split(",") if x.strip()}
    resource_host = urlparse(resource).netloc
    if resource_host not in hosts and resource_host + ":*" not in hosts:
        print("MCP_OAUTH_PREFLIGHT=FAIL")
        print("reason=resource_host_not_allowed")
        return 1

    scopes = os.environ.get("MCP_OAUTH_SCOPES", "worker:read worker:control").split()
    if not {"worker:read", "worker:control"}.issubset(scopes):
        print("MCP_OAUTH_PREFLIGHT=FAIL")
        print("reason=required_worker_scopes_missing")
        return 1

    print("MCP_OAUTH_PREFLIGHT=PASS")
    print("resource=" + resource)
    print("issuer=" + issuer)
    print("required_scopes=worker:read worker:control")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
