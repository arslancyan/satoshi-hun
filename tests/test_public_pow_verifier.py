from challenge_adapters.public_pow_verifier import verify


def test_public_pow_verifier_accepts_known_vector():
    result = verify(
        "satoshi-hunt-public-pow-v1",
        4,
        42792,
        "00005eafeffacb9217a2cb1b7b5dc0fffa4037e4bafc88e69d0ea5ddfec8750a",
        max_nonce=1048575,
    )
    assert result["valid"] is True


def test_public_pow_verifier_rejects_out_of_range_nonce():
    result = verify(
        "satoshi-hunt-public-pow-v1",
        4,
        1048576,
        "00005eafeffacb9217a2cb1b7b5dc0fffa4037e4bafc88e69d0ea5ddfec8750a",
        max_nonce=1048575,
    )
    assert result["valid"] is False
    assert result["reason"] == "nonce_out_of_range"


def test_public_pow_verifier_rejects_wrong_hash():
    result = verify(
        "satoshi-hunt-public-pow-v1",
        4,
        42792,
        "deadbeef",
        max_nonce=1048575,
    )
    assert result["valid"] is False
