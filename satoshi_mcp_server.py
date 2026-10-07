import os
from typing import Any
import httpx
from pydantic import AnyHttpUrl
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.middleware.auth_context import get_access_token

API_URL = os.environ.get("SATOSHI_HUNT_API", "https://satoshi-hunt-api-production.up.railway.app").rstrip("/")
OAUTH_ISSUER = os.environ.get("MCP_OAUTH_ISSUER", "").strip().rstrip("/")
RESOURCE_URL = os.environ.get("MCP_RESOURCE_URL", "").strip().rstrip("/")
INTROSPECTION_URL = os.environ.get("MCP_OAUTH_INTROSPECTION_URL", "").strip()
OAUTH_CLIENT_ID = os.environ.get("MCP_OAUTH_CLIENT_ID", "").strip()
OAUTH_CLIENT_SECRET = os.environ.get("MCP_OAUTH_CLIENT_SECRET", "").strip()
INTERNAL_SECRET = os.environ.get("MCP_INTERNAL_SECRET", "").strip()
REQUIRED_SCOPES = ["worker:read", "worker:control"]

class IntrospectionVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        if not (INTROSPECTION_URL and OAUTH_ISSUER and RESOURCE_URL):
            return None
        auth = (OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET) if OAUTH_CLIENT_ID else None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    INTROSPECTION_URL,
                    data={"token": token, "resource": RESOURCE_URL},
                    auth=auth,
                )
                if response.status_code != 200:
                    return None
                claims = response.json()
        except Exception:
            return None
        if claims.get("active") is not True:
            return None
        if claims.get("iss") and str(claims["iss"]).rstrip("/") != OAUTH_ISSUER:
            return None
        audience = claims.get("aud", claims.get("resource"))
        if isinstance(audience, str):
            audience = [audience]
        if RESOURCE_URL not in (audience or []):
            return None
        scopes = str(claims.get("scope", "")).split()
        if not all(scope in scopes for scope in REQUIRED_SCOPES):
            return None
        subject = str(claims.get("sub") or "")
        if not subject:
            return None
        return AccessToken(
            token=token,
            client_id=str(claims.get("client_id") or claims.get("azp") or "mcp-client"),
            scopes=scopes,
            resource=RESOURCE_URL,
            subject=subject,
            claims=claims,
            expires_at=int(claims["exp"]) if claims.get("exp") else None,
        )

auth_settings = None
token_verifier = None
if OAUTH_ISSUER and RESOURCE_URL and INTROSPECTION_URL:
    auth_settings = AuthSettings(
        issuer_url=AnyHttpUrl(OAUTH_ISSUER),
        resource_server_url=AnyHttpUrl(RESOURCE_URL),
        required_scopes=REQUIRED_SCOPES,
        validate_token_resource=True,
    )
    token_verifier = IntrospectionVerifier()

mcp = FastMCP(
    "Satoshi Hunt Worker Control",
    instructions=(
        "Worker-only control surface for Satoshi Hunt. Never perform admin, "
        "funding, payout configuration, registry mutation, database access, "
        "private-key/seed operations, or research-only work."
    ),
)

async def _get(path: str, token: str | None = None) -> Any:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(API_URL + path, headers=headers)
        r.raise_for_status()
        return r.json()

async def _post(path: str, payload: dict | None = None, token: str | None = None) -> Any:
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(API_URL + path, headers=headers, json=payload or {})
        r.raise_for_status()
        return r.json()

async def _oauth_api_token() -> str:
    access = get_access_token()
    if access is None:
        raise RuntimeError("Worker OAuth authorization is required")
    if not INTERNAL_SECRET:
        raise RuntimeError("MCP_INTERNAL_SECRET is not configured")
    claims = access.claims or {}
    payload = {"subject": access.subject or "", "email": claims.get("email") or claims.get("preferred_username")}
    headers = {"X-MCP-Internal-Secret": INTERNAL_SECRET}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(API_URL + "/internal/mcp/session", headers=headers, json=payload)
        r.raise_for_status()
        return r.json()["session"]

def _token(ctx: Context) -> str:
    auth = (ctx.headers or {}).get("authorization", "")
    if not auth.startswith("Bearer "):
        raise RuntimeError("Worker authorization is required")
    return auth[7:].strip()

async def _api_token(ctx: Context) -> str:
    if token_verifier is not None:
        return await _oauth_api_token()
    return _token(ctx)

@mcp.tool()
async def satoshi_status(ctx: Context) -> dict:
    """Show the connected Satoshi Hunt worker account status."""
    return await _get("/me", await _api_token(ctx))

@mcp.tool()
async def list_live_puzzles(ctx: Context) -> dict:
    """List the live marketplace puzzles and their server-computed queue eligibility."""
    return await _get("/marketplace/challenges", await _api_token(ctx))

@mcp.tool()
async def get_puzzle(challenge_id: str, ctx: Context) -> dict:
    """Get one live puzzle's funding, verification and adapter metadata."""
    return await _get(f"/marketplace/challenges/{challenge_id}", await _api_token(ctx))

@mcp.tool()
async def get_worker_status(ctx: Context) -> dict:
    """Return active workers and their current assignments for the connected account."""
    token = await _api_token(ctx)
    workers = await _get("/workers", token)
    result = []
    for worker in workers:
        assignments = await _get(f"/workers/{worker['id']}/assignments", token)
        result.append({**worker, "assignments": assignments})
    return {"workers": result}

@mcp.tool()
async def get_worker_jobs(ctx: Context) -> list:
    """List jobs visible to the connected Satoshi Hunt account."""
    return await _get("/jobs", await _api_token(ctx))

@mcp.tool()
async def get_telemetry(challenge_id: str, ctx: Context) -> dict:
    """Return marketplace telemetry and adaptive metrics for a puzzle."""
    puzzle = await get_puzzle(challenge_id, ctx)
    return {
        "challenge_id": challenge_id,
        "search_metrics": puzzle.get("search_metrics"),
        "expected_value_score": puzzle.get("expected_value_score"),
        "verification": puzzle.get("verification"),
        "live_verification": puzzle.get("live_verification"),
    }

@mcp.tool()
async def get_reward_status(ctx: Context) -> dict:
    """Show the connected account's reward balance and withdrawal status."""
    return await _get("/account/rewards", await _api_token(ctx))

@mcp.tool()
async def rank_puzzles(ctx: Context, limit: int = 20) -> dict:
    """Return current adaptive ranking, limited to the live marketplace."""
    data = await list_live_puzzles(ctx)
    rows = data.get("challenges", data.get("offers", []))
    return {"challenges": rows[:max(1, min(limit, 100))]}

@mcp.tool()
async def check_queue_eligibility(challenge_id: str, ctx: Context) -> dict:
    """Return the server-computed eligibility decision for one puzzle."""
    puzzle = await get_puzzle(challenge_id, ctx)
    verification = puzzle.get("verification") or {}
    payout = puzzle.get("payout") or {}
    reasons = []
    if puzzle.get("status") != "OPEN + FUNDED": reasons.append("not_open_funded")
    if float(puzzle.get("balance_btc") or 0) <= 0: reasons.append("no_positive_balance")
    if puzzle.get("funding_match") is not True: reasons.append("funding_not_verified")
    if puzzle.get("verification_stale") is not False: reasons.append("verification_stale")
    if verification.get("execution_mode") != "COMPUTE": reasons.append("execution_mode_not_compute")
    if verification.get("adapter_audited") is not True: reasons.append("adapter_not_audited")
    if verification.get("adapter_runnable") is not True: reasons.append("adapter_not_runnable")
    if payout.get("permissionless") is not True: reasons.append("payout_not_permissionless")
    if payout.get("automatic_chain_claim") is not True: reasons.append("automatic_chain_claim_disabled")
    return {"challenge_id": challenge_id, "eligible": not reasons, "reasons": reasons}

@mcp.tool()
async def run_puzzle(challenge_id: str, worker_id: str, ctx: Context) -> dict:
    """Run an eligible puzzle for the connected worker; server enforces the final gate."""
    data = await list_live_puzzles(ctx)
    row = next((x for x in data.get("challenges", []) if x.get("challenge_id") == challenge_id), None)
    if not row:
        return {"ok": False, "blocked": True, "challenge_id": challenge_id, "reasons": ["challenge_not_live"]}
    if row.get("queue_eligible") is not True:
        return {"ok": False, "blocked": True, "challenge_id": challenge_id, "reasons": ["central_queue_gate_rejected"]}
    return await _post(f"/marketplace/challenges/{challenge_id}/run", {"worker_id": worker_id}, await _api_token(ctx))

@mcp.tool()
async def pause_puzzle(assignment_id: str, ctx: Context) -> dict:
    """Pause the connected worker's assignment."""
    return await _post(f"/assignments/{assignment_id}/pause", {}, await _api_token(ctx))

@mcp.tool()
async def stop_puzzle(assignment_id: str, ctx: Context) -> dict:
    """Stop the connected worker's assignment."""
    return await _post(f"/assignments/{assignment_id}/stop", {}, await _api_token(ctx))

@mcp.tool()
async def switch_puzzle(challenge_id: str, worker_id: str, ctx: Context) -> dict:
    """Atomically switch the connected worker to an eligible puzzle."""
    return await run_puzzle(challenge_id, worker_id, ctx)

@mcp.tool()
async def restart_worker(worker_id: str, ctx: Context) -> dict:
    """Request a worker heartbeat/control refresh; never grants new permissions."""
    return await _post(f"/workers/{worker_id}/heartbeat", {}, await _api_token(ctx))

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
