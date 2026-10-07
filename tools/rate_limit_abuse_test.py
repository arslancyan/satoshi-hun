#!/usr/bin/env python3
"""Staging Redis-backed rate-limit abuse gate."""
import json, os, time, urllib.error, urllib.request

BASE=os.environ.get("SATOSHI_HUNT_API","http://127.0.0.1:8000").rstrip("/")

def main():
    hits=[]
    for i in range(8):
        req=urllib.request.Request(
            BASE+"/auth/register",
            data=json.dumps({"email":f"rate-test-{i}@example.com","password":"Rate-Test-Only-2026!"}).encode(),
            headers={"Content-Type":"application/json","X-Forwarded-For":"198.51.100.77"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req,timeout=10) as response:
                hits.append(response.status)
        except urllib.error.HTTPError as exc:
            hits.append(exc.code)
        time.sleep(0.05)
    if 429 not in hits:
        raise SystemExit(f"rate-limit gate failed: expected 429, got {hits}")
    print("rate-limit gate PASS:", hits)

if __name__ == "__main__":
    main()
