"""Verifier for Peter Todd's public hash-collision bounty family.

This adapter verifies only the published mathematical condition:
two distinct byte strings must have equal digest under the named hash.
It never handles private keys, seed phrases, wallet credentials, or spending.
"""
import hashlib

class PeterToddHashCollisionAdapter:
    challenge_type = "hash-collision"

    def verify(self, record, candidate_hash):
        value = str(candidate_hash)
        parts = value.split(":", 2)
        if len(parts) != 3:
            return False
        algorithm, a_hex, b_hex = parts
        if algorithm.lower() not in {"sha256", "ripemd160", "hash160", "hash256"}:
            return False
        try:
            a = bytes.fromhex(a_hex)
            b = bytes.fromhex(b_hex)
        except ValueError:
            return False
        if not a or not b or a == b or len(a) > 520 or len(b) > 520:
            return False
        if algorithm.lower() == "sha256":
            da = hashlib.sha256(a).digest()
            db = hashlib.sha256(b).digest()
        elif algorithm.lower() == "ripemd160":
            da = hashlib.new("ripemd160", a).digest()
            db = hashlib.new("ripemd160", b).digest()
        elif algorithm.lower() == "hash160":
            da = hashlib.new("ripemd160", hashlib.sha256(a).digest()).digest()
            db = hashlib.new("ripemd160", hashlib.sha256(b).digest()).digest()
        else:
            da = hashlib.sha256(hashlib.sha256(a).digest()).digest()
            db = hashlib.sha256(hashlib.sha256(b).digest()).digest()
        return da == db

ADAPTER = PeterToddHashCollisionAdapter()
