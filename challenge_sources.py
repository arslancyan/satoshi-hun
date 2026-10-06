"""Live public-challenge source adapters with independent on-chain funding verification."""
import json, os, re, urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

SOURCE_URL = os.getenv(
    "PUBLIC_CHALLENGE_SOURCE_URL",
    "https://raw.githubusercontent.com/floflo777/open-crypto-puzzles/main/puzzles.json",
)
BITCOIN_EXPLORER_BASE = os.getenv(
    "BITCOIN_EXPLORER_BASE", "https://blockstream.info/api"
).rstrip("/")
ETH_RPC_URL = os.getenv("ETH_RPC_URL", "").strip()


def _fetch_json(url, timeout=20):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Satoshi-Hunt-ChallengeSource/1.1"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _parse_expected_sats(value):
    """Parse the catalog's optional per-escrow expected amount."""
    if value is None:
        return None
    text = str(value).strip().lower().replace(",", "")
    if text in {"", "n/a", "na", "unknown"}:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(btc|sats?|sat)?", text)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2) or ""
    return int(round(amount * 100_000_000)) if unit == "btc" else int(round(amount))


def _published_reward_sats(puzzle):
    prize = puzzle.get("prize") or {}
    asset = str(prize.get("asset", "")).lower()
    amount = prize.get("amount")
    if amount is None or asset not in {"btc", "sats", "sat"}:
        return None
    return (
        int(round(float(amount) * 100_000_000))
        if asset == "btc"
        else int(round(float(amount)))
    )


@dataclass(frozen=True)
class LiveSourceRecord:
    id: str
    title: str
    chain: str
    reward_btc: float
    balance_btc: float
    status: str
    provenance: dict[str, Any]
    verification: dict[str, Any]
    payout: dict[str, Any]
    addresses: list[dict[str, Any]]
    challenge_type: str
    source_adapter: str

    def as_registry(self):
        return {
            "id": self.id,
            "title": self.title,
            "challenge_type": self.challenge_type,
            "reward_btc": self.reward_btc,
            "balance_btc": self.balance_btc,
            "status": self.status,
            "rules": "public-reward-challenge",
            "provenance": self.provenance,
            "verification": self.verification,
            "payout": self.payout,
            "addresses": self.addresses,
            "source_adapter": self.source_adapter,
        }


class BitcoinEsploraAdapter:
    def __init__(self, base_url=BITCOIN_EXPLORER_BASE):
        self.base_url = base_url.rstrip("/")

    def state(self, address):
        return _fetch_json(f"{self.base_url}/address/{address}")

    def utxos(self, address):
        return _fetch_json(f"{self.base_url}/address/{address}/utxo")

    def tx(self, txid):
        return _fetch_json(f"{self.base_url}/tx/{txid}")

    def outspend(self, txid, vout):
        return _fetch_json(f"{self.base_url}/tx/{txid}/outspend/{vout}")

    def confirmed_balance_sats(self, address):
        state = self.state(address)
        stats = state.get("chain_stats", {})
        return max(
            0,
            int(stats.get("funded_txo_sum", 0))
            - int(stats.get("spent_txo_sum", 0)),
        )


class EthereumJsonRpcAdapter:
    def __init__(self, rpc_url=ETH_RPC_URL):
        self.rpc_url = rpc_url

    def balance(self, address):
        if not self.rpc_url:
            raise RuntimeError("ETH_RPC_URL is not configured")
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "eth_getBalance",
                "params": [address, "finalized"],
                "id": 1,
            }
        ).encode()
        req = urllib.request.Request(
            self.rpc_url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Satoshi-Hunt-ChallengeSource/1.1",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.load(response)
        if data.get("error"):
            raise RuntimeError(str(data["error"]))
        return int(data["result"], 16)


def _is_custodial(puzzle):
    text = " ".join(
        [
            str(puzzle.get("difficulty_note", "")),
            str((puzzle.get("prize") or {}).get("note", "")),
        ]
    ).lower()
    return any(
        x in text
        for x in (
            "custodial",
            "paid by hand",
            "manual verification",
            "manual pay",
            "organizer",
        )
    )


def _escrows(puzzle):
    return [
        x
        for x in (puzzle.get("addresses") or [])
        if x.get("role") == "escrow"
        and x.get("address")
        and x.get("chain") in ("bitcoin", "ethereum")
    ]


class OpenCryptoPuzzlesAdapter:
    adapter_id = "open-crypto-puzzles-v2"

    def __init__(self):
        self.btc = BitcoinEsploraAdapter()
        self.eth = EthereumJsonRpcAdapter()

    def discover(self):
        catalog = _fetch_json(SOURCE_URL)
        rows = catalog.get("puzzles", []) if isinstance(catalog, dict) else []
        out = []

        for puzzle in rows:
            if puzzle.get("status") != "open" or _is_custodial(puzzle):
                continue

            addresses = _escrows(puzzle)
            if not addresses:
                continue

            # This adapter currently activates BTC only. We do not silently
            # convert or compare BTC rewards against another asset.
            if str(puzzle.get("chain", "")).lower() != "bitcoin":
                continue

            published_sats = _published_reward_sats(puzzle)
            if published_sats is None or published_sats <= 0:
                continue

            live_addresses = []
            total_sats = 0
            address_errors = []

            for item in addresses:
                if item.get("chain") != "bitcoin":
                    continue
                try:
                    live_sats = self.btc.confirmed_balance_sats(item["address"])
                    expected_sats = _parse_expected_sats(item.get("expected"))
                    live_addresses.append(
                        {
                            **item,
                            "expected_sats": expected_sats,
                            "live_balance_sats": live_sats,
                            "live_balance_btc": live_sats / 100_000_000,
                            "live_checked_at": _now(),
                        }
                    )
                    # A catalog address marked swept is retained for evidence,
                    # but does not contribute to the live prize.
                    if item.get("verified_state") != "swept":
                        total_sats += live_sats
                except Exception as exc:
                    address_errors.append(
                        {"address": item["address"], "error": str(exc)}
                    )

            # A partial explorer failure is never interpreted as "empty" or
            # "solved". The sync worker will preserve the previous DB state.
            if address_errors or not live_addresses:
                continue

            funding_match = total_sats >= published_sats
            balance_btc = total_sats / 100_000_000
            status = "OPEN + FUNDED" if funding_match and total_sats > 0 else "OPEN + UNFUNDED"

            provenance = {
                "url": (puzzle.get("published") or {}).get("url") or SOURCE_URL,
                "source_id": puzzle.get("slug"),
                "catalog_url": SOURCE_URL,
                "catalog_last_updated": puzzle.get("last_updated"),
                "checked_at": _now(),
            }
            verification = {
                "method": "live-public-escrow",
                "source_id": self.adapter_id,
                "checked_at": _now(),
                "fingerprint": str(puzzle.get("slug")),
                "oracle_certified": bool(
                    (puzzle.get("derivation") or {}).get("oracle_certified")
                ),
                "advertised_reward_btc": published_sats / 100_000_000,
                "verified_balance_btc": balance_btc,
                "funding_match": funding_match,
                "funding_delta_btc": (total_sats - published_sats) / 100_000_000,
                "confirmed_only": True,
                "verification_stale": False,
                "addresses": live_addresses,
            }
            payout = {
                "mode": "DIRECT_PUBLIC_ESCROW",
                "permissionless": True,
                "automatic_chain_claim": True,
                "automatic_platform_signing": False,
                "claim_evidence": "on-chain payout transaction",
                "asset": "BTC",
            }

            out.append(
                LiveSourceRecord(
                    str(puzzle["slug"]),
                    str(puzzle.get("title", puzzle["slug"])),
                    "bitcoin",
                    published_sats / 100_000_000,
                    balance_btc,
                    status,
                    provenance,
                    verification,
                    payout,
                    live_addresses,
                    str((puzzle.get("puzzle_type") or ["public-puzzle"])[0]),
                    self.adapter_id,
                )
            )
        return out


def discover_live_challenges():
    return [x.as_registry() for x in OpenCryptoPuzzlesAdapter().discover()]


if __name__ == "__main__":
    print(json.dumps(discover_live_challenges(), indent=2))
