from anti_cheat import reputation_score


def test_reputation_score_neutral():
    assert reputation_score(0, 0, 0, 0, 0, 0) == 50.0
