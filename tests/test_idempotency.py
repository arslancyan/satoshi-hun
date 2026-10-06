import hashlib
import json


def fingerprint(method, path, payload):
    canonical = json.dumps({"method": method, "path": path, "payload": payload}, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(canonical).hexdigest()


def test_idempotency_fingerprint_is_stable_for_key_order():
    a = fingerprint("POST", "/workers", {"label": "cpu", "x": 1})
    b = fingerprint("POST", "/workers", {"x": 1, "label": "cpu"})
    assert a == b


def test_idempotency_fingerprint_changes_for_different_request():
    a = fingerprint("POST", "/workers", {"label": "cpu"})
    b = fingerprint("POST", "/workers", {"label": "gpu"})
    assert a != b


def test_idempotency_fingerprint_binds_method_and_path():
    a = fingerprint("POST", "/workers", {"label": "cpu"})
    b = fingerprint("PUT", "/workers/123/capabilities", {"label": "cpu"})
    assert a != b


def test_idempotency_key_reuse_requires_same_request_fingerprint():
    first = fingerprint("POST", "/creator/offers", {"challenge_id": "135", "estimated_seconds": 10})
    same = fingerprint("POST", "/creator/offers", {"estimated_seconds": 10, "challenge_id": "135"})
    changed = fingerprint("POST", "/creator/offers", {"challenge_id": "135", "estimated_seconds": 11})
    assert first == same
    assert first != changed


def worker_fingerprint(worker_id, method, path, payload):
    canonical = json.dumps(
        {"worker_id": worker_id, "method": method, "path": path, "payload": payload},
        sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def test_worker_idempotency_is_scoped_to_worker():
    a = worker_fingerprint("worker-a", "POST", "/assignments/1/heartbeat", {})
    b = worker_fingerprint("worker-b", "POST", "/assignments/1/heartbeat", {})
    assert a != b


def test_worker_idempotency_is_stable_for_same_worker_request():
    a = worker_fingerprint("worker-a", "POST", "/assignments/1/checkpoint", {"cursor_next": 10, "nonce": "n"})
    b = worker_fingerprint("worker-a", "POST", "/assignments/1/checkpoint", {"nonce": "n", "cursor_next": 10})
    assert a == b
