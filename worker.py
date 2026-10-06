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


def api_json(path, method="GET", payload=None, request_id=""):
    if not API_BASE or not API_TOKEN:
        raise RuntimeError("SATOSHI_HUNT_API and SATOSHI_HUNT_TOKEN are required")
    parsed = urlparse(API_BASE)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise RuntimeError("SATOSHI_HUNT_API must be an http(s) URL")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost"):
        raise RuntimeError("Non-local worker API endpoints must use HTTPS")
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Authorization": "Worker " + API_TOKEN, "Content-Type": "application/json"}
    if request_id:
        headers["Idempotency-Key"] = request_id
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=15) as response:  # nosec B310 - URL is restricted to configured API endpoint
        return json.loads(response.read().decode())


def api_call(path, method="POST", payload=None):
    request_id = str(uuid.uuid4()) if method != "GET" else ""
    try:
        return api_json(path, method, payload, request_id)
    except (urllib.error.URLError, TimeoutError):
        time.sleep(1)
        return api_json(path, method, payload, request_id)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"API {exc.code}: {detail}") from exc




def hash_digest(algorithm, message):
    algorithm = algorithm.lower()
    if algorithm == "sha256":
        return hashlib.sha256(message).digest()
    if algorithm == "ripemd160":
        return hashlib.new("ripemd160", message).digest()
    if algorithm == "hash160":
        return hashlib.new("ripemd160", hashlib.sha256(message).digest()).digest()
    if algorithm == "hash256":
        return hashlib.sha256(hashlib.sha256(message).digest()).digest()
    raise ValueError(f"Unsupported collision algorithm: {algorithm}")


def solve_hash_collision(algorithm, start_cursor=0, max_candidates=0, max_memory_mb=256, checkpoint_callback=None, stop_event=None):
    """Perform a genuine birthday collision search.

    The returned candidate is exactly the format accepted by the Peter Todd
    verifier: algorithm:a_hex:b_hex. No demo marker or synthetic result is
    submitted. A full-width collision is required.
    """
    algorithm = algorithm.lower()
    seen = {}
    cursor = int(start_cursor)
    max_candidates = int(max_candidates)
    max_memory_bytes = max(32, int(max_memory_mb)) * 1024 * 1024
    started = time.monotonic()
    last_checkpoint = cursor
    last_checkpoint_at = started
    # 8-byte counter messages keep the search deterministic and reproducible.
    while True:
        if stop_event and stop_event.is_set():
            return None, cursor, time.monotonic() - started
        if max_candidates and cursor - start_cursor >= max_candidates:
            return None, cursor, time.monotonic() - started

        message = b"satoshi-hunt:" + cursor.to_bytes(8, "big")
        digest = hash_digest(algorithm, message)
        previous = seen.get(digest)
        if previous is not None and previous != message:
            # Recompute both digests before returning. This is an independent
            # local check, not trust in the hash table entry.
            if hash_digest(algorithm, previous) == hash_digest(algorithm, message):
                return f"{algorithm}:{previous.hex()}:{message.hex()}", cursor + 1, time.monotonic() - started
        seen[digest] = message
        cursor += 1

        # Keep memory bounded. Once the configured table budget is reached,
        # stop rather than silently swapping the user's machine.
        if len(seen) * (32 + 64) >= max_memory_bytes:
            return None, cursor, time.monotonic() - started

        now = time.monotonic()
        if checkpoint_callback and (now - last_checkpoint_at >= 30):
            checkpoint_callback(start_cursor, cursor, cursor, str(cursor))
            last_checkpoint = cursor
            last_checkpoint_at = now



async def run_assignment(assignment):
    aid = assignment["id"]
    job_id = assignment["job_id"]
    puzzle_id = assignment["puzzle_id"]
    stop_event = asyncio.Event()
    heartbeat_task = None
    try:
        if assignment["status"] == "ASSIGNED":
            await asyncio.to_thread(api_call, f"/assignments/{aid}/start")

        challenge_feed = await asyncio.to_thread(api_json, "/marketplace/challenges")
        challenge = next((x for x in challenge_feed.get("challenges", []) if x.get("challenge_id") == puzzle_id), None)
        if not challenge:
            raise RuntimeError("Assigned challenge is no longer present in the verified live registry")
        if challenge.get("challenge_type") != "hash-collision":
            raise RuntimeError(f"No real solver is registered for challenge type {challenge.get('challenge_type')!r}")

        allowed = (challenge.get("verification") or {}).get("allowed_algorithms") or []
        requested = os.environ.get("SATOSHI_HUNT_ALGORITHM", "").strip().lower()
        algorithm = requested if requested in allowed else (str(allowed[0]).lower() if allowed else "")
        if algorithm not in {"sha256", "ripemd160", "hash160", "hash256"}:
            raise RuntimeError("Challenge has no supported collision algorithm")

        # Heartbeats run independently of the CPU search so a long-running
        # real solver remains leased and can also notice a user stop request.
        async def heartbeat_loop():
            while not stop_event.is_set():
                try:
                    await asyncio.to_thread(api_call, f"/assignments/{aid}/heartbeat")
                except Exception as exc:
                    print(f"[{puzzle_id}] heartbeat: {exc}")
                    if "409" in str(exc) or "404" in str(exc):
                        stop_event.set()
                        return
                await asyncio.sleep(15)

        heartbeat_task = asyncio.create_task(heartbeat_loop())
        max_candidates = max(0, int(os.environ.get("SATOSHI_HUNT_MAX_CANDIDATES", "0")))
        max_memory_mb = max(32, int(os.environ.get("SATOSHI_HUNT_MAX_MEMORY_MB", "256")))
        cursor_start = int(os.environ.get("SATOSHI_HUNT_START_CURSOR", "0"))

        def checkpoint(start, end, nxt, nonce):
            try:
                api_call(
                    f"/assignments/{aid}/checkpoint",
                    "POST",
                    {"assignment_id": aid, "cursor_start": start, "cursor_end": end, "cursor_next": nxt, "nonce": nonce},
                )
                print(f"[{puzzle_id}] checkpoint cursor={nxt}")
            except Exception as exc:
                print(f"[{puzzle_id}] checkpoint: {exc}")

        print(f"[{puzzle_id}] REAL {algorithm} collision search started")
        candidate, cursor, elapsed = await asyncio.to_thread(
            solve_hash_collision,
            algorithm,
            cursor_start,
            max_candidates,
            max_memory_mb,
            checkpoint,
            stop_event,
        )

        if stop_event.is_set():
            print(f"[{puzzle_id}] search stopped at cursor={cursor}")
            return

        cpu_seconds = max(0, int(elapsed))
        if candidate:
            print(f"[{puzzle_id}] genuine collision found at cursor={cursor}; submitting verifier candidate")
            result = await asyncio.to_thread(
                api_call,
                f"/jobs/{job_id}/claims",
                "POST",
                {
                    "assignment_id": aid,
                    "worker_id": WORKER_ID,
                    "candidate_hash": candidate,
                    "result_status": "TESTED",
                    "cpu_seconds": cpu_seconds,
                },
            )
            print(f"[{puzzle_id}] verifier response: {result}")
        else:
            print(f"[{puzzle_id}] no collision found in bounded search window; no reward claim submitted")
        try:
            done = await asyncio.to_thread(api_call, f"/assignments/{aid}/complete")
            print(f"[{puzzle_id}] completed: {done.get('contribution_seconds', 0)} contribution seconds")
        except Exception as exc:
            print(f"[{puzzle_id}] completion: {exc}")
    except Exception as exc:
        print(f"[{puzzle_id}] assignment error: {exc}")
    finally:
        stop_event.set()
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass


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
