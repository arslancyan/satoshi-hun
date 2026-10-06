from anti_cheat import reputation_score


def test_reputation_score_neutral():
    assert reputation_score(0, 0, 0, 0, 0, 0) == 50.0


def test_reputation_score_penalizes_negative_signals():
    clean = reputation_score(20, 10, 0, 0, 10, 36000)
    degraded = reputation_score(20, 1, 10, 4, 6, 36000)
    assert clean > degraded
    assert 0 <= degraded <= 100
