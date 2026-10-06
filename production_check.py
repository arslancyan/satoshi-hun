"""Production configuration preflight for Satoshi Hunt.

This is intentionally side-effect free: it validates deployment configuration
only and never connects to wallets, signs transactions, or mutates a database.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _secret_ok(name: str, minimum: int = 32) -> Check:
    value = os.environ.get(name, "")
    return Check(name, len(value) >= minimum, f"configured={bool(value)}, length={len(value)}")


def run_preflight(production: bool = True) -> list[Check]:
    checks = [
        Check("DATABASE_URL", bool(os.environ.get("DATABASE_URL", "")), "database URL configured"),
        _secret_ok("JWT_SECRET", 32),
        _secret_ok("CHALLENGE_INGESTION_KEY", 32),
        Check("OWNER_EMAIL", bool(os.environ.get("OWNER_EMAIL", "").strip()), "owner identity configured"),
        Check(
            "RATE_LIMIT_REDIS_URL",
            bool(os.environ.get("RATE_LIMIT_REDIS_URL", "")),
            "shared rate-limit store configured",
        ),
    ]

    origin = os.environ.get("FRONTEND_ORIGIN", "").strip()
    if production:
        checks.append(
            Check(
                "FRONTEND_ORIGIN",
                origin.startswith("https://") and "*" not in origin,
                "production origin must be explicit HTTPS and never wildcard",
            )
        )
    else:
        checks.append(Check("FRONTEND_ORIGIN", bool(origin), "frontend origin configured"))

    try:
        max_active = int(os.environ.get("MAX_ACTIVE_ASSIGNMENTS", "100"))
        checks.append(Check("MAX_ACTIVE_ASSIGNMENTS", max_active > 0, f"value={max_active}"))
    except ValueError:
        checks.append(Check("MAX_ACTIVE_ASSIGNMENTS", False, "must be an integer"))

    try:
        per_job = int(os.environ.get("MAX_ACTIVE_ASSIGNMENTS_PER_JOB", "1"))
        checks.append(Check("MAX_ACTIVE_ASSIGNMENTS_PER_JOB", per_job == 1, f"value={per_job}; production requires 1"))
    except ValueError:
        checks.append(Check("MAX_ACTIVE_ASSIGNMENTS_PER_JOB", False, "must be an integer"))

    try:
        worker_hours = int(os.environ.get("MAX_NETWORK_WORKER_HOURS_PER_DAY", "10000"))
        checks.append(Check("MAX_NETWORK_WORKER_HOURS_PER_DAY", worker_hours > 0, f"value={worker_hours}"))
    except ValueError:
        checks.append(Check("MAX_NETWORK_WORKER_HOURS_PER_DAY", False, "must be an integer"))

    return checks


def main() -> int:
    checks = run_preflight(production=os.environ.get("SATOSHI_HUNT_ENV", "production").lower() == "production")
    for check in checks:
        print(f"[{'OK' if check.ok else 'FAIL'}] {check.name}: {check.detail}")
    return 0 if all(check.ok for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
