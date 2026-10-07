# Production MCP OAuth setup

Satoshi Hunt exposes MCP as a protected resource. Production ChatGPT access must use an external OAuth 2.1 authorization server and a short-lived Satoshi Hunt worker session.

## Required configuration

Set these Railway variables on the existing API service:

- `MCP_ENABLED=true`
- `MCP_OAUTH_ISSUER=https://YOUR-AUTHORITY`
- `MCP_RESOURCE_URL=https://satoshi-hunt-api-production.up.railway.app/mcp`
- `MCP_OAUTH_JWKS_URL=https://YOUR-AUTHORITY/.well-known/jwks.json`
- `MCP_OAUTH_AUDIENCE=https://satoshi-hunt-api-production.up.railway.app/mcp`
- `MCP_OAUTH_INTROSPECTION_URL=...` (optional fallback; omit when using JWT/JWKS)
- `MCP_OAUTH_CLIENT_ID=...` (only when your provider requires a confidential client)
- `MCP_OAUTH_CLIENT_SECRET=...` (only when your provider requires it)
- `MCP_INTERNAL_SECRET=<long random secret>`
- `MCP_ALLOWED_HOSTS=satoshi-hunt-api-production.up.railway.app,satoshi-hunt-api-production.up.railway.app:*`

The authorization server must issue both `worker:read` and `worker:control`. The preferred production path is a signed RS256 JWT access token verified against the provider JWKS. The token audience must equal `MCP_OAUTH_AUDIENCE`; the issuer must equal `MCP_OAUTH_ISSUER`. The MCP resource remains the exact URL above.

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


## Auth0 production configuration

Use one Auth0 tenant as the external authorization server.

1. Create an API in Auth0 with Identifier:
   `https://satoshi-hunt-api-production.up.railway.app/mcp`
2. Keep RS256 signing enabled.
3. Enable Dynamic Client Registration for third-party MCP clients.
4. Enable the Auth0 Resource Parameter Compatibility Profile so the MCP `resource` parameter is accepted by Auth0.
5. Allow user-delegated access to the API and configure the login connection(s) users may use.
6. Ensure issued access tokens contain the scopes `worker:read worker:control`.
7. Set Railway:
   - `MCP_ENABLED=true`
   - `MCP_OAUTH_ISSUER=https://YOUR_TENANT.us.auth0.com`
   - `MCP_RESOURCE_URL=https://satoshi-hunt-api-production.up.railway.app/mcp`
   - `MCP_OAUTH_AUDIENCE=https://satoshi-hunt-api-production.up.railway.app/mcp`
   - `MCP_OAUTH_JWKS_URL=https://YOUR_TENANT.us.auth0.com/.well-known/jwks.json`
   - `MCP_INTERNAL_SECRET=<long random secret>`
8. In ChatGPT, add the remote MCP server using the exact production MCP URL and select OAuth. ChatGPT performs authorization-code + PKCE; do not paste a user access token into Satoshi Hunt.

### Redirect URI

For an issuer that satisfies OpenAI's issuer-identification requirements, use:
`https://chatgpt.com/connector_platform_oauth_redirect`.

Otherwise use the callback-specific redirect URI shown by the ChatGPT MCP connection UI. Configure the exact URI in Auth0.

### Important

Do not use the Auth0 Management API token as the MCP access token. Satoshi Hunt only accepts end-user access tokens issued for the MCP API audience and required worker scopes.

