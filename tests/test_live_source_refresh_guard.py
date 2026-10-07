from live_source_worker import _runtime_locked


class FakeCursor:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))

    def fetchone(self):
        return (self.value,)


def test_running_challenge_is_locked():
    cur = FakeCursor(True)
    assert _runtime_locked(cur, "challenge-1") is True
    assert cur.calls
    assert cur.calls[0][1] == ("challenge-1",)


def test_idle_challenge_is_not_locked():
    cur = FakeCursor(False)
    assert _runtime_locked(cur, "challenge-1") is False


def test_lock_query_only_allows_running_assignment_or_job():
    cur = FakeCursor(True)
    _runtime_locked(cur, "challenge-1")
    query = cur.calls[0][0]
    assert "ja.status='RUNNING'" in query
    assert "j.status='RUNNING'" in query
