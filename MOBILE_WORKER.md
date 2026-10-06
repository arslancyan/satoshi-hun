# Satoshi Hunt Mobile Worker

The mobile worker is an explicit opt-in worker for Android/Termux and other lightweight Linux environments.

## What it does

- Connects only to the Satoshi Hunt API over **HTTPS**.
- Uses a Worker token; it does not use account JWT credentials.
- Polls for assignments with battery-friendly intervals.
- Sends heartbeats while idle and while working.
- Re-reads server assignment state after connectivity loss instead of creating local duplicate jobs.
- Keeps the server as the source of truth for assignment lifecycle, contribution accounting, claims, verification, and rewards.

## What it does not do

- No private keys or seed phrases.
- No wallet credential collection.
- No private/unauthorized challenge solving.
- No hidden/background execution.
- No automatic Bitcoin payout.
- It does not invent a successful solution. A real challenge requires its approved public-challenge adapter and server-side verification.

## Android / Termux setup

Install Python in Termux, then from the repository:

```bash
pkg update
pkg install python
python --version
```

Run the mobile worker with environment variables:

```bash
export SATOSHI_HUNT_API="https://YOUR-BETA-API"
export SATOSHI_HUNT_TOKEN="YOUR_WORKER_TOKEN"
export SATOSHI_HUNT_WORKER_ID="YOUR_WORKER_ID"

python mobile_worker.py
```

For a single connectivity/assignment check:

```bash
export SATOSHI_HUNT_MOBILE_RUN_ONCE=1
python mobile_worker.py
```

Optional battery/network tuning:

```bash
export SATOSHI_HUNT_MOBILE_POLL_SECONDS=30
export SATOSHI_HUNT_MOBILE_ACTIVE_POLL_SECONDS=10
export SATOSHI_HUNT_MOBILE_HEARTBEAT_SECONDS=30
export SATOSHI_HUNT_MOBILE_MAX_BACKOFF_SECONDS=300
```

The worker adds a small random polling jitter so multiple phones do not all hit the API at exactly the same instant.

## Five-phone beta

For five phones, register five separate worker devices and give each device its own Worker token and Worker ID. Do not share one token between phones.

Recommended initial settings:

- idle poll: 30 seconds
- active poll: 10 seconds
- heartbeat: 30 seconds
- one active assignment per public challenge
- explicit user opt-in on every device

A phone should stay on reliable Wi-Fi or mobile data while working. Android battery optimization may suspend Python/Termux processes, so a mobile worker should be treated as an intermittent beta worker rather than a guaranteed 24/7 compute node.

## Important beta boundary

The current `mobile_worker.py` contains a bounded protocol placeholder. It intentionally does **not** pretend that a demo candidate is a real Bitcoin puzzle solution.

Before a public BTC reward challenge is enabled, Satoshi Hunt still needs:

1. An independently verified public challenge record.
2. Its approved challenge-specific computation adapter.
3. Server-side candidate verification.
4. A real staging acceptance test.
5. Manual owner-gated reward settlement.

This preserves the existing safety and economic model while making the worker transport mobile-friendly.
