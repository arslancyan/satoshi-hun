# Production MCP OAuth setup

Satoshi Hunt exposes MCP as a protected resource. Production ChatGPT access must use an external OAuth 2.1 authorization server and a short-lived Satoshi Hunt worker session.

## Required configuration

Set these Railway variables on the existing API service:

- `MCP_ENABLED=true`
- `MCP_OAUTH_ISSUER=https://YOUR-AUTHORITY`
- `MCP_RESOURCE_URL=https://satoshi-hunt-api-production.up.railway.app/mcp`
- `MCP_OAUTH_INTROSPECTION_URL=https://YOUR-AUTHORITY/introspect` (only for providers that support RFC 7662 introspection)
- `MCP_OAUTH_CLIENT_ID=...`
- `MCP_OAUTH_CLIENT_SECRET=...`
- `MCP_INTERNAL_SECRET=<long random secret>`
- `MCP_ALLOWED_HOSTS=satoshi-hunt-api-production.up.railway.app,satoshi-hunt-api-production.up.railway.app:*`

The authorization server must issue both `worker:read` and `worker:control` and bind the access token to the exact resource URL above.

## Account linking

Do not use email as the permanent authorization key. The production account link should be:

`(issuer, subject) -> accounts.id`

The migration `020_mcp_oauth_identities.sql` creates that mapping table. The account UI should create the link only after the user has authenticated to Satoshi Hunt and completed the provider authorization flow.

The current internal exchange endpoint remains fail-closed: it accepts a validated OAuth identity and creates a short-lived native Satoshi Hunt session; the external OAuth bearer token is never forwarded to downstream worker APIs.

## ChatGPT connection

After OAuth metadata and client registration are configured, add the Satoshi Hunt MCP endpoint as a remote MCP server in the ChatGPT client. The client must complete OAuth discovery/authorization rather than receiving a static bearer token.

## Security boundary

The MCP tool set remains worker-only:

- read: status, live puzzles, worker jobs, telemetry, rewards, ranking, queue eligibility
- control: run, pause, stop, switch, heartbeat/control refresh
- never expose admin, treasury, payout signing, registry mutation, database, private keys, or research-only solver operations

The browser worker should remain open because ChatGPT controls the assignment; it does not host the worker process itself.

## Go-plan limitation

Whether the ChatGPT UI exposes custom remote MCP write/control actions is product/plan dependent. Do not label the button "connected" until a real OAuth connection has been tested end-to-end.
