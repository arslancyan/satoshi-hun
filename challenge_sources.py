"""Live public-challenge source adapters with independent on-chain funding verification."""
import json, os, re, urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from challenge_adapters import get_adapter, runtime_contract

AUTHORITATIVE_ESCROW_SPEND_SLUGS = set(filter(None, os.getenv("AUTHORITATIVE_ESCROW_SPEND_SLUGS", "peter-todd-hash-collision-bounties-0-59btc").split(",")))
PUBLIC_CHALLENGE_SLUGS = set(filter(None, os.getenv("PUBLIC_CHALLENGE_SLUGS", "").split(",")))
ID_ALIASES = {}
for _pair in filter(None, os.getenv("CHALLENGE_ID_ALIASES", "peter-todd-hash-collision-bounties-0-59btc:peter-todd-hash-collision-bounties").split(",")):
    _src, _dst = _pair.split(":", 1)
    ID_ALIASES[_src] = _dst

SOURCE_URL = os.getenv(
    "PUBLIC_CHALLENGE_SOURCE_URL",
    "https://raw.githubusercontent.com/floflo777/open-crypto-puzzles/main/puzzles.json",
)
BITCOIN_EXPLORER_BASE = os.getenv(
    "BITCOIN_EXPLORER_BASE", "https://blockstream.info/api"
).rstrip("/")
MEMPOOL_EXPLORER_BASE = os.getenv(
    "MEMPOOL_EXPLORER_BASE", "https://mempool.space/api"
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
    search_metrics: dict[str, Any] | None = None

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
            "search_metrics": self.search_metrics or {},
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

    def exact_outspend_evidence(self, utxos):
        evidence = []
        for u in utxos:
            try:
                spend = self.outspend(u["txid"], int(u["vout"]))
            except Exception:
                continue
            if spend.get("spent") and spend.get("txid"):
                txid = spend["txid"]
                evidence.append({
                    "funding_txid": u["txid"],
                    "funding_vout": int(u["vout"]),
                    "funding_value_sats": int(u["value"]),
                    "spending_txid": txid,
                    "spending_vin": spend.get("vin"),
                    "spend_status": spend.get("status") or {},
                    "evidence_url": self.base_url + "/tx/" + txid,
                })
        return evidence

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



def _counts_toward_prize(item):
    label = str(item.get("label", "")).lower()
    excluded = (
        "not counted as prize",
        "not part of the live prize",
        "not part of live prize",
        "certification reference",
        "reference sibling",
        "demo card",
        "creator controlled",
        "solved by a third party",
        "swept",
    )
    return not any(marker in label for marker in excluded)

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
        self.mempool = BitcoinEsploraAdapter(MEMPOOL_EXPLORER_BASE)
        self.eth = EthereumJsonRpcAdapter()

    def discover(self):
        catalog = _fetch_json(SOURCE_URL)
        rows = catalog.get("puzzles", []) if isinstance(catalog, dict) else []
        out = []

        for puzzle in rows:
            if PUBLIC_CHALLENGE_SLUGS and puzzle.get("slug") not in PUBLIC_CHALLENGE_SLUGS:
                continue
            if puzzle.get("status") not in ("open", "watch") or _is_custodial(puzzle):
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
                    secondary_sats = self.mempool.confirmed_balance_sats(item["address"])
                    if live_sats != secondary_sats:
                        raise RuntimeError(
                            f"explorer disagreement: blockstream={live_sats}, mempool={secondary_sats}"
                        )
                    expected_sats = _parse_expected_sats(item.get("expected"))
                    utxos = self.btc.utxos(item["address"])
                    live_addresses.append(
                        {
                            **item,
                            "expected_sats": expected_sats,
                            "live_balance_sats": live_sats,
                            "secondary_balance_sats": secondary_sats,
                            "live_balance_btc": live_sats / 100_000_000,
                            "live_checked_at": _now(),
                            "live_utxos": [
                                {"txid":u.get("txid"),"vout":int(u.get("vout",0)),
                                 "value":int(u.get("value",0))}
                                for u in utxos
                            ],
                        }
                    )
                    # Only explicitly prize-bearing escrows count. Addresses
                    # described by the source as references, creator-controlled,
                    # demos, solved/swept, or otherwise outside the live prize
                    # are retained for audit evidence but never inflate reward.
                    counts_toward_prize = _counts_toward_prize(item) and expected_sats is not None and expected_sats > 0
                    live_addresses[-1]["counts_toward_prize"] = counts_toward_prize
                    if counts_toward_prize:
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
            difficulty_left = str(puzzle.get("difficulty_left", "") or "")
            difficulty_note = str(puzzle.get("difficulty_note", "") or "")
            leads = puzzle.get("leads") or []
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
                "counted_escrow_sats": total_sats,
                "funding_delta_btc": (total_sats - published_sats) / 100_000_000,
                "confirmed_only": True,
                "verification_stale": False,
                "addresses": live_addresses,
                "dual_explorer_match": True,
                "solve_evidence_policy": "exact-escrow-utxo-spend-required",
                "escrow_spend_is_authoritative": puzzle.get("slug") in AUTHORITATIVE_ESCROW_SPEND_SLUGS,
                "difficulty_left": difficulty_left,
                "difficulty_note": difficulty_note,
                "leads": leads[:5],
                "execution_mode": "RESEARCH",
            }
            payout = {
                "mode": "DIRECT_PUBLIC_ESCROW",
                "permissionless": True,
                "automatic_chain_claim": True,
                "automatic_platform_signing": False,
                "claim_evidence": "on-chain payout transaction",
                "asset": "BTC",
            }

            # Peter Todd contains four independently funded live escrows.
            # Expose each escrow as its own runnable puzzle so hunters can
            # choose SHA-256, RIPEMD-160, HASH160, or HASH256 separately.
            if puzzle.get("slug") == "peter-todd-hash-collision-bounties-0-59btc":
                algorithm_by_label = {
                    "SHA-256": ("sha256", "peter-todd-sha256-bounty"),
                    "RIPEMD-160": ("ripemd160", "peter-todd-ripemd160-bounty"),
                    "HASH160 (RIPEMD160(SHA256()))": ("hash160", "peter-todd-hash160-bounty"),
                    "HASH256 (SHA256(SHA256()))": ("hash256", "peter-todd-hash256-bounty"),
                }
                for live_item in live_addresses:
                    if not live_item.get("counts_toward_prize"):
                        continue
                    label = str(live_item.get("label", "")).strip()
                    match = algorithm_by_label.get(label)
                    if not match:
                        continue
                    algorithm, stable_id = match
                    expected = int(live_item.get("expected_sats") or 0)
                    live_sats = int(live_item.get("live_balance_sats") or 0)
                    per_funding_match = expected > 0 and live_sats >= expected
                    per_balance_btc = live_sats / 100_000_000
                    adapter = get_adapter(stable_id)
                    adapter_contract = runtime_contract(stable_id)
                    per_verification = {
                        **verification,
                        "fingerprint": stable_id,
                        "allowed_algorithms": [algorithm],
                        "escrow_address": live_item["address"],
                        "counted_escrow_sats": live_sats,
                        "advertised_reward_btc": expected / 100_000_000,
                        "verified_balance_btc": per_balance_btc,
                        "funding_match": per_funding_match,
                        "escrow_spend_is_authoritative": True,
                        "execution_mode": adapter_contract["execution_mode"] if adapter_contract["adapter_registered"] else "RESEARCH",
                        "adapter_id": adapter_contract.get("adapter_id"),
                        "adapter_status": adapter_contract.get("adapter_status"),
                        "adapter_runnable": adapter_contract.get("runnable", False),
                        "difficulty_left": "research-breakthrough",
                        "difficulty_note": "Hash-collision bounty; generic full-width collision search is computationally infeasible.",
                        "search_metrics": puzzle.get("search_metrics") or puzzle.get("runtime_metrics") or {},
                    }
                    per_provenance = {
                        **provenance,
                        "source_id": stable_id,
                        "parent_source_id": puzzle.get("slug"),
                    }
                    per_payout = {**payout, "claim_target": live_item["address"]}
                    out.append(
                        LiveSourceRecord(
                            stable_id,
                            f"Peter Todd — {label} Bounty",
                            "bitcoin",
                            expected / 100_000_000,
                            per_balance_btc,
                            "OPEN + FUNDED" if per_funding_match and live_sats > 0 else "OPEN + UNFUNDED",
                            per_provenance,
                            per_verification,
                            per_payout,
                            [live_item],
                            "hash-collision",
                            self.adapter_id,
                            per_verification.get("search_metrics") or {},
                        )
                    )
            else:
                adapter = get_adapter(str(puzzle["slug"]))
                adapter_contract = runtime_contract(str(puzzle["slug"]))
                verification["execution_mode"] = adapter_contract["execution_mode"]
                verification["adapter_id"] = adapter_contract.get("adapter_id")
                verification["adapter_status"] = adapter_contract.get("adapter_status")
                verification["adapter_runnable"] = adapter_contract.get("runnable", False)
                verification["search_metrics"] = puzzle.get("search_metrics") or puzzle.get("runtime_metrics") or {}
                out.append(
                    LiveSourceRecord(
                        ID_ALIASES.get(str(puzzle["slug"]), str(puzzle["slug"])),
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
                        verification.get("search_metrics") or {},
                    )
                )
        return out



def exact_escrow_spend_evidence(adapter, verification):
    """Return exact spend evidence without declaring a solve."""
    evidence = []
    for address in (verification or {}).get("addresses", []):
        evidence.extend(adapter.exact_outspend_evidence(address.get("live_utxos", [])))
    return evidence

def discover_live_challenges():
    return [x.as_registry() for x in OpenCryptoPuzzlesAdapter().discover()]


if __name__ == "__main__":
    print(json.dumps(discover_live_challenges(), indent=2))
