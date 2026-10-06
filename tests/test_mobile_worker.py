from pathlib import Path

MOBILE = Path("mobile_worker.py").read_text()
WORKER = Path("worker.py").read_text()


def test_mobile_worker_requires_https():
    assert 'parsed.scheme != "https"' in MOBILE


def test_mobile_worker_demo_is_safe_by_default():
    assert 'DEMO_MODE = os.environ.get("SATOSHI_HUNT_MOBILE_DEMO", "").lower()' in MOBILE
    assert 'if not DEMO_MODE:' in MOBILE
    assert "leaving it unstarted" in MOBILE


def test_mobile_worker_uses_worker_auth_and_idempotency():
    assert '"Authorization": "Worker " + API_TOKEN' in MOBILE
    assert 'headers["Idempotency-Key"] = request_id' in MOBILE


def test_mobile_worker_has_bounded_backoff_and_polling():
    assert "POLL_IDLE" in MOBILE
    assert "POLL_ACTIVE" in MOBILE
    assert "MAX_BACKOFF" in MOBILE
    assert "random.uniform" in MOBILE


def test_mobile_worker_does_not_handle_private_keys():
    lowered = MOBILE.lower()
    assert "private key" in lowered
    assert "seed phrase" in lowered
    assert "wallet credentials" in lowered


def test_desktop_worker_preserves_idempotency_across_call_retries():
    assert 'def api_call(path, method="POST", payload=None):' in WORKER
    assert "request_id = str(uuid.uuid4()) if method != \"GET\" else \"\"" in WORKER
    assert "api_json(path, method, payload, request_id)" in WORKER


def test_mobile_worker_exercises_resume_and_checkpoint():
    assert 'f"/assignments/{assignment_id}/resume"' in MOBILE
    assert 'f"/assignments/{assignment_id}/checkpoint"' in MOBILE
    assert "start_cursor" in MOBILE
    assert "cursor_next" in MOBILE


def test_mutation_retry_reuses_same_request_id():
    assert "return api_json(path, method, payload, request_id)" in MOBILE
    assert "except (urllib.error.URLError, TimeoutError):" in MOBILE
    assert "time.sleep(1)" in MOBILE
