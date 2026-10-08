#!/usr/bin/env python3
"""Single Railway process for challenge sync + optional official native worker.

The sync job remains periodic, while the official worker is long-lived when
its three worker credentials are configured. No credentials are hard-coded.
"""
import asyncio
import os
import subprocess
import sys
import time


SYNC_INTERVAL = max(300, int(os.environ.get("CHALLENGE_SYNC_INTERVAL_SECONDS", "1800")))


def run_sync_once():
    print("[supervisor] running challenge registry sync", flush=True)
    result = subprocess.run(
        [sys.executable, "live_source_worker.py"],
        check=False,
    )
    print(f"[supervisor] challenge sync exited rc={result.returncode}", flush=True)
    return result.returncode


async def run_worker():
    if not (
        os.environ.get("SATOSHI_HUNT_API")
        and os.environ.get("SATOSHI_HUNT_TOKEN")
        and os.environ.get("SATOSHI_HUNT_WORKER_ID")
    ):
        print(
            "[supervisor] official worker disabled: SATOSHI_HUNT_API, "
            "SATOSHI_HUNT_TOKEN and SATOSHI_HUNT_WORKER_ID are required",
            flush=True,
        )
        return
    import worker
    print(
        f"[supervisor] official native worker starting for {worker.WORKER_ID}",
        flush=True,
    )
    await worker.assignment_loop()


async def sync_loop():
    while True:
        try:
            await asyncio.to_thread(run_sync_once)
        except Exception as exc:
            print(f"[supervisor] sync error: {exc}", flush=True)
        await asyncio.sleep(SYNC_INTERVAL)


async def main():
    await asyncio.gather(sync_loop(), run_worker())


if __name__ == "__main__":
    asyncio.run(main())
