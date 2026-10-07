import os
from typing import Any
import httpx
from mcp.server.fastmcp import FastMCP

API_URL = os.environ.get("SATOSHI_HUNT_API", "https://satoshi-hunt-api-production.up.railway.app").rstrip("/")
# Development/testing credential. Production ChatGPT connections should use OAuth 2.1
# and pass the resulting Satoshi Hunt worker-scoped bearer token to this service.
MCP_BEARER = os.environ.get("SATOSHI_HUNT_MCP_BEARER", "").strip()

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

def _token() -> str:
    if not MCP_BEARER:
        raise RuntimeError("MCP worker authorization is not configured")
    return MCP_BEARER

@mcp.tool()
async def satoshi_status() -> dict:
    """Show the connected Satoshi Hunt worker account status."""
    return await _get("/me", _token())

@mcp.tool()
async def list_live_puzzles() -> dict:
    """List the live marketplace puzzles and their server-computed queue eligibility."""
    return await _get("/marketplace/challenges", _token())

@mcp.tool()
async def get_puzzle(challenge_id: str) -> dict:
    """Get one live puzzle's funding, verification and adapter metadata."""
    return await _get(f"/marketplace/challenges/{challenge_id}", _token())

@mcp.tool()
async def get_worker_status() -> dict:
    """Return active workers and their current assignments for the connected account."""
    token = _token()
    workers = await _get("/workers", token)
    result = []
    for worker in workers:
        assignments = await _get(f"/workers/{worker['id']}/assignments", token)
        result.append({**worker, "assignments": assignments})
    return {"workers": result}

@mcp.tool()
async def get_worker_jobs() -> list:
    """List jobs visible to the connected Satoshi Hunt account."""
    return await _get("/jobs", _token())

@mcp.tool()
async def get_telemetry(challenge_id: str) -> dict:
    """Return marketplace telemetry and adaptive metrics for a puzzle."""
    puzzle = await get_puzzle(challenge_id)
    return {
        "challenge_id": challenge_id,
        "search_metrics": puzzle.get("search_metrics"),
        "expected_value_score": puzzle.get("expected_value_score"),
        "verification": puzzle.get("verification"),
        "live_verification": puzzle.get("live_verification"),
    }

@mcp.tool()
async def get_reward_status() -> dict:
    """Show the connected account's reward balance and withdrawal status."""
    return await _get("/account/rewards", _token())

@mcp.tool()
async def rank_puzzles(limit: int = 20) -> dict:
    """Return current adaptive ranking, limited to the live marketplace."""
    data = await list_live_puzzles()
    rows = data.get("challenges", data.get("offers", []))
    return {"challenges": rows[:max(1, min(limit, 100))]}

@mcp.tool()
async def check_queue_eligibility(challenge_id: str) -> dict:
    """Return the server-computed eligibility decision for one puzzle."""
    puzzle = await get_puzzle(challenge_id)
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
async def run_puzzle(challenge_id: str, worker_id: str) -> dict:
    """Run an eligible puzzle for the connected worker; server enforces the final gate."""
    gate = await check_queue_eligibility(challenge_id)
    if not gate["eligible"]:
        return {"ok": False, "blocked": True, "challenge_id": challenge_id, "reasons": gate["reasons"]}
    return await _post(f"/marketplace/challenges/{challenge_id}/run", {"worker_id": worker_id}, _token())

@mcp.tool()
async def pause_puzzle(assignment_id: str) -> dict:
    """Pause the connected worker's assignment."""
    return await _post(f"/assignments/{assignment_id}/pause", {}, _token())

@mcp.tool()
async def stop_puzzle(assignment_id: str) -> dict:
    """Stop the connected worker's assignment."""
    return await _post(f"/assignments/{assignment_id}/stop", {}, _token())

@mcp.tool()
async def switch_puzzle(challenge_id: str, worker_id: str) -> dict:
    """Atomically switch the connected worker to an eligible puzzle."""
    return await run_puzzle(challenge_id, worker_id)

@mcp.tool()
async def restart_worker(worker_id: str) -> dict:
    """Request a worker heartbeat/control refresh; never grants new permissions."""
    return await _post(f"/workers/{worker_id}/heartbeat", {}, _token())

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
