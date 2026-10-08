"""Satoshi Hunt-authored permissionless bounded BTC escrow source.

Each challenge uses a P2WSH script:
    OP_SHA256 <digest> OP_EQUALVERIFY OP_TRUE
and is promoted only after the exact escrow address is independently funded.
"""
import hashlib, json, os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from challenge_sources import BitcoinEsploraAdapter
from challenge_discovery import adapter_readiness

MANIFEST = os.path.join(os.path.dirname(__file__), "challenges", "satoshi-hunt-native-btc-v2.json")

def _now():
    return datetime.now(timezone.utc).isoformat()

@dataclass(frozen=True)
class BoundedEscrowRecord:
    id: str
    title: str
    reward_btc: float
    balance_btc: float
    status: str
    verification: dict[str, Any]
    provenance: dict[str, Any]
    payout: dict[str, Any]
    addresses: list[dict[str, Any]]
    search_metrics: dict[str, Any]

    def as_registry(self):
        return {
            "id": self.id,
            "title": self.title,
            "challenge_type": "sha256-preimage-pow",
            "reward_btc": self.reward_btc,
            "balance_btc": self.balance_btc,
            "status": self.status,
            "rules": "public-reward-challenge",
            "provenance": self.provenance,
            "verification": self.verification,
            "payout": self.payout,
            "addresses": self.addresses,
            "source_adapter": "satoshi-hunt-bounded-escrow-v1",
            "search_metrics": self.search_metrics,
        }

class SatoshiHuntBoundedEscrowAdapter:
    adapter_id = "satoshi-hunt-bounded-escrow-v1"

    def __init__(self):
        self.btc = BitcoinEsploraAdapter()

    def discover(self):
        with open(MANIFEST, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
        out=[]
        for puzzle in manifest.get("challenges", []):
            challenge_id = str(puzzle["id"])
            difficulty_bits = int(puzzle["difficulty_bits"])
            max_nonce = int(puzzle["max_nonce"])
            reward_btc = float(puzzle["reward_btc"])
            address = str(puzzle["escrow_address"])
            live_sats = self.btc.confirmed_balance_sats(address)
            reward_sats = int(round(reward_btc * 100_000_000))
            funding_match = live_sats >= reward_sats and live_sats > 0
            readiness = adapter_readiness(challenge_id)
            contract = readiness["adapter"]
            verification = {
                "method": "permissionless-p2wsh-sha256-preimage",
                "source_id": self.adapter_id,
                "checked_at": _now(),
                "fingerprint": challenge_id,
                "advertised_reward_btc": reward_btc,
                "verified_balance_btc": live_sats / 100_000_000,
                "funding_match": funding_match,
                "confirmed_only": True,
                "verification_stale": False,
                "dual_explorer_match": False,
                "escrow_spend_is_authoritative": True,
                "execution_mode": "COMPUTE" if readiness["execution_allowed"] else "RESEARCH",
                "adapter_id": contract.get("adapter_id"),
                "adapter_status": contract.get("adapter_status"),
                "adapter_audited": bool(contract.get("adapter_audited")),
                "adapter_runnable": readiness["execution_allowed"],
                "adapter_execution_allowed": readiness["execution_allowed"],
                "adapter_readiness": readiness["readiness"],
                "adapter_reason": readiness["reason"],
                "difficulty_bits": difficulty_bits,
                "max_nonce": max_nonce,
                "claim_method": "P2WSH_SHA256_PREIMAGE",
                "witness_script_hex": puzzle["witness_script_hex"],
                "witness_program_sha256": puzzle["witness_program_sha256"],
            }
            address_row = {
                "address": address,
                "chain": "bitcoin",
                "role": "escrow",
                "label": f"{difficulty_bits}-bit bounded preimage escrow",
                "expected_sats": reward_sats,
                "live_balance_sats": live_sats,
                "live_balance_btc": live_sats / 100_000_000,
                "live_checked_at": _now(),
                "counts_toward_prize": True,
                "live_utxos": [
                    {"txid":u["txid"],"vout":int(u["vout"]),"value":int(u["value"])}
                    for u in self.btc.utxos(address)
                ],
            }
            provenance = {
                "url": "https://github.com/arslancyan/satoshi-hun",
                "source_id": challenge_id,
                "manifest": "challenges/satoshi-hunt-native-btc-v2.json",
                "checked_at": _now(),
            }
            payout = {
                "mode": "DIRECT_PUBLIC_ESCROW",
                "permissionless": True,
                "automatic_chain_claim": True,
                "automatic_platform_signing": False,
                "claim_evidence": "on-chain payout transaction",
                "asset": "BTC",
                "claim_target": address,
            }
            metrics = {
                "keyspace_total": max_nonce + 1,
                "keyspace_searched": 0,
                "difficulty_bits": difficulty_bits,
            }
            out.append(BoundedEscrowRecord(
                challenge_id, str(puzzle["title"]), reward_btc,
                live_sats / 100_000_000,
                "OPEN + FUNDED" if funding_match else "OPEN + UNFUNDED",
                verification, provenance, payout, [address_row], metrics
            ))
        return out
