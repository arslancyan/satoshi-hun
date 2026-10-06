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
