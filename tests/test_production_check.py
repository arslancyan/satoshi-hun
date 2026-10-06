from production_check import run_preflight


def test_production_preflight_requires_shared_rate_limit_store(monkeypatch):
    values = {
        "DATABASE_URL": "postgresql://example",
        "JWT_SECRET": "x" * 32,
        "CHALLENGE_INGESTION_KEY": "y" * 32,
        "OWNER_EMAIL": "owner@example.com",
        "FRONTEND_ORIGIN": "https://example.com",
        "RATE_LIMIT_REDIS_URL": "redis://example",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    checks = {check.name: check for check in run_preflight()}
    assert checks["RATE_LIMIT_REDIS_URL"].ok
    assert checks["FRONTEND_ORIGIN"].ok
    assert checks["MAX_ACTIVE_ASSIGNMENTS_PER_JOB"].ok


def test_production_preflight_rejects_weak_secrets_and_wildcard_origin(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("JWT_SECRET", "short")
    monkeypatch.setenv("CHALLENGE_INGESTION_KEY", "short")
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")
    monkeypatch.setenv("FRONTEND_ORIGIN", "*")
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "redis://example")

    checks = {check.name: check for check in run_preflight()}
    assert not checks["JWT_SECRET"].ok
    assert not checks["CHALLENGE_INGESTION_KEY"].ok
    assert not checks["FRONTEND_ORIGIN"].ok


def test_production_preflight_requires_single_active_assignment_per_job(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.setenv("CHALLENGE_INGESTION_KEY", "y" * 32)
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://example.com")
    monkeypatch.setenv("RATE_LIMIT_REDIS_URL", "redis://example")
    monkeypatch.setenv("MAX_ACTIVE_ASSIGNMENTS_PER_JOB", "2")

    checks = {check.name: check for check in run_preflight()}
    assert not checks["MAX_ACTIVE_ASSIGNMENTS_PER_JOB"].ok
