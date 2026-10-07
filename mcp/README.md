# Satoshi Hunt — ChatGPT Worker Control

This directory defines the least-privilege MCP contract for connecting a Satoshi Hunt worker account to ChatGPT.

## Scope

ChatGPT is a **worker operator**, never an administrator. The MCP layer must authorize every request against the connected Satoshi Hunt account and expose only worker-scoped tools.

### Read tools
- satoshi_status — worker/account connection status.
- list_live_puzzles — live marketplace puzzles and queue eligibility.
- get_puzzle — one puzzle state, telemetry and adapter provenance.
- get_worker_status — connected worker status and active assignment.
- get_worker_jobs — assignments visible to the connected worker.
- get_telemetry — measured worker/challenge telemetry.
- get_reward_status — worker reward balance and withdrawal status.
- rank_puzzles — current adaptive ranking.
- check_queue_eligibility — server-side queue gate result.

### Control tools
- run_puzzle — start/switch to one eligible puzzle.
- pause_puzzle — pause the current assignment.
- stop_puzzle — stop the current assignment.
- switch_puzzle — atomically pause the current puzzle and run another eligible puzzle.
- restart_worker — restart the worker process/control lease only.

## Hard security boundary

The MCP layer must reject requests for admin operations, challenge registry mutation, funding or payout configuration, arbitrary database access, private keys/seed phrases/wallet credentials, research-only or unaudited adapters, and challenges that fail the centralized queue gate.

run_puzzle and switch_puzzle must call the same centralized challenge_registry_policy.queue_gate() used by the normal worker queue. MCP must never implement a second eligibility policy.

## Browser worker behavior

The Satoshi Hunt browser account page remains open. ChatGPT does not execute heavy computation inside the ChatGPT conversation. It only changes the worker assignment/control state through the Satoshi Hunt API.

The browser worker UI continues polling/heartbeating its assignment. If the browser is closed, the normal heartbeat timeout/recovery rules apply; ChatGPT cannot keep a browser process alive after the user closes it.

## Authentication

The core Satoshi Hunt product does **not** depend on MCP authentication or an external OAuth provider.

The browser worker, marketplace, adaptive scheduler, queue gate, account-level one-active-puzzle rule, telemetry and reward lifecycle operate directly through the normal Satoshi Hunt API.

The MCP/ChatGPT layer is optional infrastructure. Do not block production worker operation on MCP, Auth0, OAuth, or ChatGPT connectivity.

If MCP is enabled later, it must retain the same worker-only security boundary and server-side queue validation described below.

## Tool annotations

Read tools: readOnlyHint=true, destructiveHint=false, openWorldHint=false.

run_puzzle: readOnlyHint=false, destructiveHint=false, openWorldHint=false.

pause_puzzle, stop_puzzle, switch_puzzle, restart_worker: readOnlyHint=false, destructiveHint=true, openWorldHint=false.

The annotations are hints only; authorization and queue validation remain server-side requirements.

## Connection UX

The Account page contains a CHATGPT · WORKER CONTROL section. It explains the permission boundary and links to the connection instructions. The actual OAuth linking UI is provided by ChatGPT when the MCP connector advertises the OAuth metadata.

## Implementation target

Expose a remote Streamable HTTP MCP endpoint at /mcp. The MCP service should call the existing Satoshi Hunt API over HTTPS, never connect directly to PostgreSQL. This preserves the existing API authorization, account-level one-active-puzzle lock, audit trail and queue gate.
## Production OAuth configuration

The MCP endpoint is an OAuth 2.1 resource server. The authorization server remains an external identity provider; the MCP SDK exposes protected-resource metadata and validates bearer tokens through the configured verifier. This follows the MCP AS/RS model rather than forwarding ChatGPT's OAuth token to the Satoshi Hunt API.

Configure these Railway environment variables before enabling MCP:

- `MCP_ENABLED=true`
- `MCP_OAUTH_ISSUER=https://<your-authority>`
- `MCP_RESOURCE_URL=https://<satoshi-hunt-host>/mcp`
- `MCP_OAUTH_INTROSPECTION_URL=https://<your-authority>/introspect`
- `MCP_OAUTH_CLIENT_ID=<resource-server-client-id>`
- `MCP_OAUTH_CLIENT_SECRET=<resource-server-client-secret>`
- `MCP_INTERNAL_SECRET=<long-random-server-secret>`
- `MCP_ALLOWED_HOSTS=<satoshi-hunt-host>,<satoshi-hunt-host>:*`

The OAuth provider must issue tokens containing the `worker:read` and `worker:control` scopes and bind the token to the exact MCP resource URL. MCP authorization guidance requires protected-resource metadata, authorization-server discovery, PKCE for authorization-code flows, and resource/audience binding.

The private `/internal/mcp/session` route exchanges a validated MCP identity for a short-lived native Satoshi Hunt session. The OAuth bearer token is never passed through to downstream Satoshi Hunt API endpoints.

Do not put `MCP_INTERNAL_SECRET`, OAuth client secrets, or Satoshi Hunt session tokens into the browser or ChatGPT instructions.