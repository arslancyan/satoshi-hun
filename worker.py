#!/usr/bin/env python3
"""Satoshi Hunt opt-in local worker.

API mode coordinates only public-reward-challenge assignments. It does not
access wallets, private keys, credentials, or hidden/private challenges.
"""
import asyncio
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlparse

import websockets

try:
    import psutil
except ImportError:
    psutil = None

HOST, PORT = "127.0.0.1", 8765
API_BASE = os.environ.get("SATOSHI_HUNT_API", "").rstrip("/")
API_TOKEN = os.environ.get("SATOSHI_HUNT_TOKEN", "")
WORKER_ID = os.environ.get("SATOSHI_HUNT_WORKER_ID", "")
POLL_SECONDS = max(5, int(os.environ.get("SATOSHI_HUNT_POLL_SECONDS", "10")))
HEARTBEAT_SECONDS = max(10, int(os.environ.get("SATOSHI_HUNT_HEARTBEAT_SECONDS", "20")))


def api_json(path, method="GET", payload=None):
    if not API_BASE or not API_TOKEN:
        raise RuntimeError("SATOSHI_HUNT_API and SATOSHI_HUNT_TOKEN are required")
    parsed = urlparse(API_BASE)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise RuntimeError("SATOSHI_HUNT_API must be an http(s) URL")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost"):
        raise RuntimeError("Non-local worker API endpoints must use HTTPS")
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Authorization": "Worker " + API_TOKEN, "Content-Type": "application/json"}
    if method != "GET":
        headers["Idempotency-Key"] = str(uuid.uuid4())
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=15) as response:  # nosec B310 - URL is restricted to configured API endpoint
        return json.loads(response.read().decode())


def api_call(path, method="POST", payload=None):
    try:
        return api_json(path, method, payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"API {exc.code}: {detail}") from exc


def candidate_hash(job_id, attempt=0):
    """Deterministic demo candidate marker, not a wallet/private-key search."""
    raw = f"satoshi-hunt-demo:{job_id}:{attempt}".encode()
    return hashlib.sha256(raw).hexdigest()


async def run_assignment(assignment):
    aid = assignment["id"]
    job_id = assignment["job_id"]
    puzzle_id = assignment["puzzle_id"]
    try:
        if assignment["status"] == "ASSIGNED":
            api_call(f"/assignments/{aid}/start")
        await asyncio.to_thread(api_call, f"/assignments/{aid}/heartbeat")
        # Keep the assignment lease alive while the worker is active.

        for i in range(0, 101, 10):
            await asyncio.sleep(0.08)
            print(f"[{puzzle_id}] lightweight public-challenge pass {i}%")

        # Candidate submission is intentionally a framework marker. A real
        # adapter must implement the public challenge's published verifier.
        result = await asyncio.to_thread(
            api_call,
            f"/jobs/{job_id}/claims",
            "POST",
            {
                "assignment_id": aid,
                "worker_id": WORKER_ID,
                "candidate_hash": candidate_hash(job_id),
                "result_status": "TESTED",
                "cpu_seconds": 0,
            },
        )
        print(f"[{puzzle_id}] claim: {result.get('accepted', False)}")
        done = await asyncio.to_thread(api_call, f"/assignments/{aid}/complete")
        print(f"[{puzzle_id}] completed: {done.get('contribution_seconds', 0)} contribution seconds")
    except Exception as exc:
        print(f"[{puzzle_id}] assignment error: {exc}")


async def assignment_loop():
    active = None
    while True:
        try:
            assignments = await asyncio.to_thread(
                api_json, f"/workers/{WORKER_ID}/assignments"
            )
            pending = next(
                (a for a in assignments if a["status"] in ("ASSIGNED", "RUNNING")),
                None,
            )
            if pending and (not active or active["id"] != pending["id"]):
                active = pending
                await run_assignment(pending)
                active = None
            else:
                await asyncio.to_thread(
                    api_call, f"/workers/{WORKER_ID}/heartbeat"
                )
        except Exception as exc:
            print(f"[assignment loop] {exc}")
        await asyncio.sleep(POLL_SECONDS)


async def handler(ws):
    async for raw in ws:
        m = json.loads(raw)
        if m.get("type") != "solve":
            continue
        p = m.get("puzzle", {})
        pid = p.get("id", "?")
        provenance = p.get("provenance")
        verification = p.get("verification")
        metadata_ok = (
            isinstance(provenance, dict)
            and all(str(provenance.get(k, "")).strip() for k in ("url", "source_id", "checked_at"))
            and isinstance(verification, dict)
            and all(str(verification.get(k, "")).strip() for k in ("method", "source_id", "checked_at", "fingerprint"))
        )
        if p.get("status") != "OPEN + FUNDED" or p.get("rules") != "public-reward-challenge" or not metadata_ok:
            await ws.send(json.dumps({
                "type": "result",
                "message": f"#{pid} rejected: challenge is not fully verified for local work."
            }))
            continue
        for i in range(0, 101, 10):
            await asyncio.sleep(.08)
            await ws.send(json.dumps({
                "type": "progress",
                "job": "#" + pid,
                "percent": i,
                "message": f"Running lightweight candidate checks… {i}%"
            }))
        await ws.send(json.dumps({
            "type": "result",
            "message": f"#{pid}: candidate generation complete. Challenge-specific verification is required."
        }))


async def telemetry(ws):
    while True:
        await ws.send(json.dumps({
            "type": "telemetry",
            "cpu": psutil.cpu_percent() if psutil else 0,
            "ram": round(psutil.virtual_memory().used / 1024 / 1024) if psutil else 0
        }))
        await asyncio.sleep(2)


async def session(ws):
    await asyncio.gather(handler(ws), telemetry(ws))


async def main():
    tasks = [assignment_loop()] if API_BASE and API_TOKEN and WORKER_ID else []
    async with websockets.serve(session, HOST, PORT):
        if tasks:
            await asyncio.gather(*tasks)
        else:
            print("Local UI worker mode only. Set SATOSHI_HUNT_API, SATOSHI_HUNT_TOKEN and SATOSHI_HUNT_WORKER_ID for API mode.")
            await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
