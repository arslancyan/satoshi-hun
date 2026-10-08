from payout_executor.escrow import build_escrow_transaction
from challenge_adapters.bounded_escrow_preimage import digest

QUICK = "satoshi-hunt-native-btc-quick-v2"
ESCROW = "bc1qq275r5a96zjh9seap6pha5tlea2mjnndy3adv4zylq2w3wgr6mnqzx7dyp"
SCRIPT = "a8200000085f05d9cf7c4c2d14ec2a07ad67c0c5e58177c128ba81eca68fdf556c198851"


def test_known_quick_nonce_matches_escrow_script():
    assert digest(QUICK, 10697) == "0000085f05d9cf7c4c2d14ec2a07ad67c0c5e58177c128ba81eca68fdf556c19"
    assert SCRIPT == "a820" + digest(QUICK, 10697) + "8851"


def test_permissionless_escrow_transaction_builds_without_signing():
    tx = build_escrow_transaction(
        challenge_id=QUICK,
        nonce=10697,
        escrow_address=ESCROW,
        witness_script_hex=SCRIPT,
        payout_address=ESCROW,
        reward_sats=10000,
        utxos=[{
            "txid": "00" * 32,
            "vout": 0,
            "value": 15000,
            "status": {"confirmed": True},
        }],
        fee_rate_sat_vb=1,
        minimum_fee_sats=300,
    )
    assert len(tx["raw_tx_hex"]) > 100
    assert len(tx["txid"]) == 64
    assert tx["payout_sats"] == 9700
    assert tx["fee_sats"] == 300
