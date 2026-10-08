from worker import solve_bounded_preimage


def test_quick_native_solver_finds_bounded_solution():
    candidate, cursor, attempts, elapsed = solve_bounded_preimage(
        "satoshi-hunt-native-btc-quick-v2", 8, 1048575
    )
    assert candidate is not None
    assert candidate["nonce"] == 243
    assert candidate["hash"].startswith("00")
    assert cursor == 244
    assert attempts == 244


def test_hard_native_solver_finds_bounded_solution():
    candidate, cursor, attempts, elapsed = solve_bounded_preimage(
        "satoshi-hunt-native-btc-hard-v2", 12, 4194303
    )
    assert candidate is not None
    assert candidate["nonce"] == 1314
    assert candidate["hash"].startswith("000")
    assert cursor == 1315


def test_extreme_native_solver_finds_bounded_solution():
    candidate, cursor, attempts, elapsed = solve_bounded_preimage(
        "satoshi-hunt-native-btc-extreme-v2", 16, 16777215
    )
    assert candidate is not None
    assert candidate["nonce"] == 47813
    assert candidate["hash"].startswith("0000")
    assert cursor == 47814
