"""Canonical registry helpers for public reward challenges."""
import hashlib
import json
from datetime import datetime, timezone


def canonical_json(record):
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def record_fingerprint(record):
    return hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()


def verification_metadata(method, source_id, record):
    return {
        "method": method,
        "source_id": source_id,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": record_fingerprint(record),
    }


def provenance_metadata(url, source_id):
    if not url.startswith(("https://", "http://")):
        raise ValueError("provenance URL must be HTTP(S)")
    return {
        "url": url,
        "source_id": source_id,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
