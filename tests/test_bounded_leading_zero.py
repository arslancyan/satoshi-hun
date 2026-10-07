from challenge_adapters.bounded_leading_zero import proof_digest, solve, verify

def test_bounded_leading_zero_known_vector():
    result = solve("satoshi-hunt-test", 8, 100000, max_attempts=100001)
    assert result is not None
    checked = verify("satoshi-hunt-test", 8, result["nonce"], result["hash"], 100000)
    assert checked["valid"] is True

def test_bounded_leading_zero_rejects_out_of_range():
    digest = proof_digest("x", 5)
    result = verify("x", 1, 6, digest, 5)
    assert result["valid"] is False
    assert result["reason"] == "nonce_out_of_range"
