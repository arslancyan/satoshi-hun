"""Non-custodial Bitcoin P2WSH escrow claim rail.

The Satoshi Hunt bounded escrow script is:
    OP_SHA256 <digest> OP_EQUALVERIFY OP_TRUE

It requires no private key. A valid preimage is the only witness item needed
to satisfy the script. This module builds and broadcasts the spend using a
public Bitcoin explorer/broadcast endpoint; it never holds signing material.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from decimal import Decimal
from typing import Any

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32M = 0x2BC830A3
MAX_TXID = 64


def _fetch_json(url: str, timeout: float = 20) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SatoshiHunt-Escrow/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310 - URL is fixed/configured public explorer
        return json.loads(response.read().decode())


def _post_text(url: str, body: bytes, timeout: float = 30) -> str:
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"User-Agent": "SatoshiHunt-Escrow/1.0", "Content-Type": "text/plain"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:  # nosec B310 - URL is fixed/configured public broadcaster
        return response.read().decode().strip()


def _sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def _varint(n: int) -> bytes:
    if n < 0:
        raise ValueError("negative varint")
    if n < 0xFD:
        return bytes([n])
    if n <= 0xFFFF:
        return b"\xfd" + n.to_bytes(2, "little")
    if n <= 0xFFFFFFFF:
        return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")


def _script_push(data: bytes) -> bytes:
    n = len(data)
    if n < 0x4C:
        return bytes([n]) + data
    if n <= 0xFF:
        return b"\x4c" + bytes([n]) + data
    if n <= 0xFFFF:
        return b"\x4d" + n.to_bytes(2, "little") + data
    return b"\x4e" + n.to_bytes(4, "little") + data


def _bech32_polymod(values: list[int]) -> int:
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ value
        for i in range(5):
            if (top >> i) & 1:
                chk ^= gen[i]
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _convertbits(data: list[int], frombits: int, tobits: int, pad: bool) -> list[int] | None:
    acc = 0
    bits = 0
    ret: list[int] = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or value >> frombits:
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def decode_bech32_address(address: str) -> bytes:
    if not address or address.lower() != address:
        raise ValueError("mixed-case or empty bech32 address")
    if not address.startswith("bc1"):
        raise ValueError("not a Bitcoin mainnet bech32 address")
    pos = address.rfind("1")
    if pos < 1 or pos + 7 > len(address):
        raise ValueError("invalid bech32 separator")
    try:
        data = [BECH32.index(c) for c in address[pos + 1:]]
    except ValueError as exc:
        raise ValueError("invalid bech32 character") from exc
    pm = _bech32_polymod(_bech32_hrp_expand(address[:pos]) + data)
    if pm not in (1, BECH32M):
        raise ValueError("invalid bech32 checksum")
    version = data[0]
    if version > 16:
        raise ValueError("invalid witness version")
    program = bytes(_convertbits(data[1:-6], 5, 8, False) or [])
    if not 2 <= len(program) <= 40:
        raise ValueError("invalid witness program length")
    if version == 0:
        if pm != 1 or len(program) not in (20, 32):
            raise ValueError("invalid v0 witness address")
    elif pm != BECH32M:
        raise ValueError("invalid bech32m witness address")
    return bytes([version if version else 0]) + bytes([len(program)]) + program


def decode_base58_address(address: str) -> bytes:
    if not address or any(c not in BASE58 for c in address):
        raise ValueError("invalid base58 address")
    n = 0
    for c in address:
        n = n * 58 + BASE58.index(c)
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    leading = len(address) - len(address.lstrip("1"))
    raw = b"\x00" * leading + raw
    if len(raw) != 25:
        raise ValueError("invalid base58check length")
    if raw[0] not in (0, 5):
        raise ValueError("not a Bitcoin mainnet base58 address")
    if _sha256d(raw[:-4])[:4] != raw[-4:]:
        raise ValueError("invalid base58check checksum")
    version, payload = raw[0], raw[1:-4]
    if version == 0:
        return b"\x00\x14" + payload
    return b"\xa9\x14" + payload + b"\x87"


def address_script_pubkey(address: str) -> bytes:
    address = str(address).strip()
    if address.startswith("bc1"):
        return decode_bech32_address(address)
    return decode_base58_address(address)


def _expected_witness_script(challenge_id: str, nonce: int) -> bytes:
    preimage = f"{challenge_id}:{int(nonce)}".encode("utf-8")
    digest = hashlib.sha256(preimage).digest()
    return b"\xa8" + b"\x20" + digest + b"\x88" + b"\x51"


def _txid_bytes(txid: str) -> bytes:
    txid = str(txid).strip()
    if len(txid) != MAX_TXID or any(c not in "0123456789abcdefABCDEF" for c in txid):
        raise ValueError("invalid funding txid")
    return bytes.fromhex(txid)[::-1]


def _estimate_vbytes(input_count: int, output_count: int, preimage_len: int, script_len: int) -> int:
    # Conservative estimate. Witness is discounted; output size uses a P2TR-sized
    # scriptPubKey so fee estimation is never optimistic for supported addresses.
    base = 4 + 1 + input_count * (36 + 1 + 4) + 1 + output_count * (8 + 1 + 34) + 4
    witness = input_count * (1 + (1 + preimage_len) + (1 + script_len))
    return (base * 4 + witness + 3) // 4


def _select_utxos(utxos: list[dict[str, Any]], needed_sats: int) -> list[dict[str, Any]]:
    confirmed = [
        u for u in utxos
        if bool((u.get("status") or {}).get("confirmed"))
        and int(u.get("value", 0)) > 0
        and u.get("txid") is not None
    ]
    confirmed.sort(key=lambda x: int(x.get("value", 0)))
    selected: list[dict[str, Any]] = []
    total = 0
    for u in confirmed:
        selected.append(u)
        total += int(u["value"])
        if total >= needed_sats:
            return selected
    raise RuntimeError("Escrow does not have enough confirmed BTC for reward plus transaction fee")


def build_escrow_transaction(
    *,
    challenge_id: str,
    nonce: int,
    escrow_address: str,
    witness_script_hex: str,
    payout_address: str,
    reward_sats: int,
    utxos: list[dict[str, Any]],
    fee_rate_sat_vb: int,
    minimum_fee_sats: int,
) -> dict[str, Any]:
    if reward_sats <= 0:
        raise ValueError("reward_sats must be positive")
    if not 0 <= int(nonce) <= 0x7FFFFFFFFFFFFFFF:
        raise ValueError("nonce out of range")

    witness_script = bytes.fromhex(str(witness_script_hex))
    expected = _expected_witness_script(challenge_id, int(nonce))
    if witness_script != expected:
        raise ValueError("witness script does not match challenge id and nonce")
    escrow_script = address_script_pubkey(escrow_address)
    if escrow_script != b"\x00\x20" + hashlib.sha256(witness_script).digest():
        raise ValueError("escrow address does not commit to the supplied witness script")
    payout_script = address_script_pubkey(payout_address)

    preimage = f"{challenge_id}:{int(nonce)}".encode("utf-8")
    fee_rate = max(1, int(fee_rate_sat_vb))
    minimum_fee = max(100, int(minimum_fee_sats))

    # First pass: choose a UTXO set large enough for reward plus a conservative
    # fee. Re-estimate after selection with the actual input/output count.
    selected = _select_utxos(utxos, reward_sats + minimum_fee)
    total_in = sum(int(u["value"]) for u in selected)
    output_count = 2 if total_in > reward_sats else 1
    fee = max(minimum_fee, fee_rate * _estimate_vbytes(len(selected), output_count, len(preimage), len(witness_script)))

    if total_in < reward_sats + fee:
        # Try additional confirmed UTXOs if the first set was short after the
        # exact fee estimate.
        remaining = [u for u in utxos if u not in selected]
        selected = _select_utxos(utxos, reward_sats + fee)
        total_in = sum(int(u["value"]) for u in selected)
        output_count = 2 if total_in > reward_sats else 1
        fee = max(minimum_fee, fee_rate * _estimate_vbytes(len(selected), output_count, len(preimage), len(witness_script)))
    if total_in < reward_sats + fee:
        raise RuntimeError("Escrow balance is insufficient after fee calculation")

    payout_value = reward_sats - fee
    if payout_value <= 0:
        raise RuntimeError("Reward is too small to pay the network fee")
    change = total_in - reward_sats

    version = (2).to_bytes(4, "little")
    marker_flag = b"\x00\x01"
    vin = _varint(len(selected))
    input_parts = []
    for u in selected:
        txid = _txid_bytes(u["txid"])
        vout = int(u["vout"]).to_bytes(4, "little")
        input_parts.append(txid + vout + b"\x00" + b"\xff\xff\xff\xff")
    vout_count = _varint(1 + (1 if change > 0 else 0))
    outputs = [
        int(payout_value).to_bytes(8, "little") + _varint(len(payout_script)) + payout_script
    ]
    if change > 0:
        outputs.append(
            int(change).to_bytes(8, "little") + _varint(len(escrow_script)) + escrow_script
        )
    witness = _varint(2) + _script_push(preimage) + _script_push(witness_script)
    witnesses = witness * len(selected)
    locktime = b"\x00\x00\x00\x00"

    raw = version + marker_flag + vin + b"".join(input_parts) + vout_count + b"".join(outputs) + witnesses + locktime
    txid_serialized = version + vin + b"".join(input_parts) + vout_count + b"".join(outputs) + locktime
    txid = _sha256d(txid_serialized)[::-1].hex()

    return {
        "raw_tx_hex": raw.hex(),
        "txid": txid,
        "input_sats": total_in,
        "payout_sats": payout_value,
        "change_sats": change,
        "fee_sats": fee,
        "input_count": len(selected),
        "output_count": 1 + (1 if change > 0 else 0),
    }


def claim_escrow(
    *,
    challenge_id: str,
    nonce: int,
    escrow_address: str,
    witness_script_hex: str,
    payout_address: str,
    reward_sats: int,
) -> dict[str, Any]:
    explorer_base = os.environ.get("ESCROW_EXPLORER_BASE", "https://mempool.space/api").rstrip("/")
    broadcaster = os.environ.get("ESCROW_BROADCAST_URL", f"{explorer_base}/tx").strip()
    fee_rate = max(1, int(os.environ.get("ESCROW_FEE_RATE_SAT_VB", "2")))
    minimum_fee = max(100, int(os.environ.get("ESCROW_MIN_FEE_SATS", "300")))

    utxos = _fetch_json(f"{explorer_base}/address/{escrow_address}/utxo")
    tx = build_escrow_transaction(
        challenge_id=challenge_id,
        nonce=nonce,
        escrow_address=escrow_address,
        witness_script_hex=witness_script_hex,
        payout_address=payout_address,
        reward_sats=int(reward_sats),
        utxos=utxos if isinstance(utxos, list) else [],
        fee_rate_sat_vb=fee_rate,
        minimum_fee_sats=minimum_fee,
    )
    returned_txid = _post_text(broadcaster, tx["raw_tx_hex"].encode("ascii"))
    if len(returned_txid) != MAX_TXID or any(c not in "0123456789abcdefABCDEF" for c in returned_txid):
        raise RuntimeError("Bitcoin broadcaster returned an invalid transaction id")
    # A broadcaster is authoritative for acceptance, but ensure it agrees with
    # our local transaction id before marking the withdrawal paid.
    if returned_txid.lower() != tx["txid"].lower():
        raise RuntimeError("Bitcoin broadcaster txid does not match locally computed txid")
    return {
        "txid": returned_txid.lower(),
        "status": "PAID",
        "payout_sats": tx["payout_sats"],
        "fee_sats": tx["fee_sats"],
        "change_sats": tx["change_sats"],
        "input_count": tx["input_count"],
        "output_count": tx["output_count"],
        "broadcast": "accepted",
    }
