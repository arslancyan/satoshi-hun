from worker import hash_digest, solve_hash_collision


def test_hash_digest_matches_real_sha256():
    assert hash_digest("sha256", b"abc").hex() == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_real_solver_emits_verifier_candidate_when_collision_exists(monkeypatch):
    def fake_digest(_algorithm, message):
        # Test harness simulates a real collision so the solver control flow
        # can be tested without attempting an infeasible production collision.
        return b"collision-digest"

    monkeypatch.setattr("worker.hash_digest", fake_digest)
    candidate, cursor, elapsed = solve_hash_collision(
        "sha256",
        start_cursor=0,
        max_candidates=10,
        max_memory_mb=32,
    )
    assert candidate is not None
    algorithm, a_hex, b_hex = candidate.split(":")
    assert algorithm == "sha256"
    assert a_hex != b_hex
    assert bytes.fromhex(a_hex) != bytes.fromhex(b_hex)
    assert cursor == 2
    assert elapsed >= 0


def test_real_solver_never_returns_demo_marker(monkeypatch):
    monkeypatch.setattr("worker.hash_digest", lambda _algorithm, message: message)
    candidate, _, _ = solve_hash_collision(
        "sha256",
        start_cursor=0,
        max_candidates=4,
        max_memory_mb=32,
    )
    assert candidate is None
