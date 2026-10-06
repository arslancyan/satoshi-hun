#!/usr/bin/env python3
"""Satoshi Hunt mobile-friendly opt-in API worker.

Designed for Android/Termux and other lightweight devices. This worker:
- uses HTTPS API mode only (no local WebSocket/UI dependency);
- polls for server assignments with an adaptive, battery-friendly interval;
- sends worker heartbeats while idle/active;
- resumes server-owned assignments after temporary connectivity loss;
- never handles private keys, seed phrases, wallet credentials, or private challenges.

The worker intentionally performs only the public-reward-challenge protocol.
Challenge-specific solving belongs in an approved adapter.
"""
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlparse

API_BASE = os.environ.get("SATOSHI_HUNT_API", "").rstrip("/")
API_TOKEN = os.environ.get("SATOSHI_HUNT_TOKEN", "")
WORKER_ID = os.environ.get("SATOSHI_HUNT_WORKER_ID", "")
POLL_IDLE = max(15, int(os.environ.get("SATOSHI_HUNT_MOBILE_POLL_SECONDS", "30")))
POLL_ACTIVE = max(5, int(os.environ.get("SATOSHI_HUNT_MOBILE_ACTIVE_POLL_SECONDS", "10")))
HEARTBEAT_SECONDS = max(20, int(os.environ.get("SATOSHI_HUNT_MOBILE_HEARTBEAT_SECONDS", "30")))
MAX_BACKOFF = max(60, int(os.environ.get("SATOSHI_HUNT_MOBILE_MAX_BACKOFF_SECONDS", "300")))
RUN_ONCE = os.environ.get("SATOSHI_HUNT_MOBILE_RUN_ONCE", "").lower() in ("1", "true", "yes")
DEMO_MODE = os.environ.get("SATOSHI_HUNT_MOBILE_DEMO", "").lower() in ("1", "true", "yes")


def validate_config():
    if not API_BASE or not API_TOKEN or not WORKER_ID:
        raise SystemExit(
            "Set SATOSHI_HUNT_API, SATOSHI_HUNT_TOKEN and SATOSHI_HUNT_WORKER_ID."
        )
    parsed = urlparse(API_BASE)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SystemExit("Mobile worker requires an HTTPS SATOSHI_HUNT_API endpoint.")


def api_json(path, method="GET", payload=None, request_id=""):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Authorization": "Worker " + API_TOKEN, "Content-Type": "application/json"}
    if request_id:
        headers["Idempotency-Key"] = request_id
    req = urllib.request.Request(
        API_BASE + path,
        data=data,
        method=method,
        headers={**headers, "User-Agent": "SatoshiHunt-MobileWorker/1.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:  # nosec B310
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


def assignments():
    result = api_json(f"/workers/{WORKER_ID}/assignments")
    if not isinstance(result, list):
        raise RuntimeError("Unexpected assignment response")
    return result


def active_assignment(items):
    return next(
        (item for item in items if item.get("status") in ("ASSIGNED", "RUNNING")),
        None,
    )


def candidate_hash(job_id, attempt=0):
    """Deterministic beta marker; never represents a Bitcoin private-key search."""
    raw = f"satoshi-hunt-mobile-demo:{job_id}:{attempt}".encode()
    return hashlib.sha256(raw).hexdigest()


def work_assignment(item):
    assignment_id = item["id"]
    job_id = item["job_id"]
    puzzle_id = item.get("puzzle_id", "?")

    if not DEMO_MODE:
        print(f"[#{puzzle_id}] assignment detected but no mobile adapter is enabled; leaving it unstarted.")
        return False

    if item.get("status") == "ASSIGNED":
        api_call(f"/assignments/{assignment_id}/start")
        print(f"[#{puzzle_id}] started")

    resume = api_call(f"/assignments/{assignment_id}/resume")
    resume_cursor = resume.get("resume_cursor")
    print(f"[#{puzzle_id}] resume cursor:", resume_cursor)

    # A server-owned assignment is resumable: reconnecting simply re-reads
    # the assignment state instead of creating a second assignment locally.
    last_heartbeat = 0.0
    started = time.monotonic()
    start_cursor = min(100, int(resume_cursor or 0) + 1)
    checkpoints = sorted(set(range(start_cursor, 101, 10)) | {100}) if start_cursor <= 100 else []

    # Bounded beta protocol placeholder. A production challenge adapter must
    # replace the marker with the published challenge computation and its
    # independently verifiable candidate.
    for progress in checkpoints:
        now = time.monotonic()
        if now - last_heartbeat >= HEARTBEAT_SECONDS:
            api_call(f"/assignments/{assignment_id}/heartbeat")
            last_heartbeat = now
        api_call(
            f"/assignments/{assignment_id}/checkpoint",
            "POST",
            {
                "cursor_start": 0,
                "cursor_end": 100,
                "cursor_next": progress,
                "nonce": f"mobile-demo-{progress}",
            },
        )
        print(f"[#{puzzle_id}] mobile public-challenge pass {progress}%")
        if progress < 100:
            time.sleep(1)

    result = api_call(
        f"/jobs/{job_id}/claims",
        "POST",
        {
            "assignment_id": assignment_id,
            "worker_id": WORKER_ID,
            "candidate_hash": candidate_hash(job_id),
            "result_status": "TESTED",
            "cpu_seconds": max(0, int(time.monotonic() - started)),
        },
    )
    print(f"[#{puzzle_id}] beta claim accepted: {result.get('accepted', False)}")
    done = api_call(f"/assignments/{assignment_id}/complete")
    print(
        f"[#{puzzle_id}] completed: "
        f"{done.get('contribution_seconds', 0)} contribution seconds"
    )


def run():
    validate_config()
    print("Satoshi Hunt Mobile Worker — explicit opt-in mode")
    print("API:", API_BASE)
    print("Worker:", WORKER_ID)
    print("Battery-friendly polling:", POLL_IDLE, "s idle /", POLL_ACTIVE, "s active")
    print("Demo protocol:", "ENABLED" if DEMO_MODE else "disabled (safe default)")

    backoff = POLL_IDLE
    last_heartbeat = 0.0

    while True:
        try:
            items = assignments()
            current = active_assignment(items)
            now = time.monotonic()

            if current:
                backoff = POLL_ACTIVE
                if now - last_heartbeat >= HEARTBEAT_SECONDS:
                    api_call(f"/workers/{WORKER_ID}/heartbeat")
                    last_heartbeat = now
                work_assignment(current)
                if RUN_ONCE:
                    return
                backoff = POLL_IDLE
            else:
                if now - last_heartbeat >= HEARTBEAT_SECONDS:
                    api_call(f"/workers/{WORKER_ID}/heartbeat")
                    last_heartbeat = now
                print("[idle] no assignment; sleeping", POLL_IDLE, "s")
                if RUN_ONCE:
                    return

            # Small jitter avoids synchronized polling when several phones
            # start together.
            time.sleep(backoff + random.uniform(0, min(5, backoff * 0.1)))
            backoff = POLL_IDLE

        except KeyboardInterrupt:
            print("\nStopped by user.")
            return
        except Exception as exc:
            print("[network]", exc)
            print("[network] retrying in", backoff, "s")
            time.sleep(backoff)
            backoff = min(MAX_BACKOFF, max(POLL_ACTIVE, backoff * 2))


if __name__ == "__main__":
    run()
