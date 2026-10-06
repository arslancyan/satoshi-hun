"""Verifier for Peter Todd's public hash-collision bounty family.

The adapter verifies only the published mathematical condition:
two distinct byte strings must have equal digest under the named hash.
It never handles private keys, seed phrases, wallet credentials, or spending.
"""

import hashlib


ESCROW_BY_ALGORITHM = {
    "sha256": "35Snmmy3uhaer2gTboc81ayCip4m9DT4ko",
    "ripemd160": "3KyiQEGqqdb4nqfhUzGKN6KPhXmQsLNpay",
    "hash160": "39VXyuoc6SXYKp9TcAhoiN1mb4ns6z3Yu6",
    "hash256": "3DUQQvz4t57Jy7jxE86kyFcNpKtURNf1VW",
}


class PeterToddHashCollisionAdapter:
    challenge_type = "hash-collision"

    def verify(self, record, candidate_hash):
        parts = str(candidate_hash).split(":", 2)
        if len(parts) != 3:
            return False

        algorithm, a_hex, b_hex = parts
        algorithm = algorithm.lower()
        allowed = set(record.get("verification", {}).get("allowed_algorithms", []))
        if algorithm not in ESCROW_BY_ALGORITHM or algorithm not in allowed:
            return False

        try:
            a = bytes.fromhex(a_hex)
            b = bytes.fromhex(b_hex)
        except ValueError:
            return False

        if not a or not b or a == b or len(a) > 520 or len(b) > 520:
            return False

        if algorithm == "sha256":
            da = hashlib.sha256(a).digest()
            db = hashlib.sha256(b).digest()
        elif algorithm == "ripemd160":
            da = hashlib.new("ripemd160", a).digest()
            db = hashlib.new("ripemd160", b).digest()
        elif algorithm == "hash160":
            da = hashlib.new("ripemd160", hashlib.sha256(a).digest()).digest()
            db = hashlib.new("ripemd160", hashlib.sha256(b).digest()).digest()
        else:
            da = hashlib.sha256(hashlib.sha256(a).digest()).digest()
            db = hashlib.sha256(hashlib.sha256(b).digest()).digest()

        return da == db


ADAPTER = PeterToddHashCollisionAdapter()
