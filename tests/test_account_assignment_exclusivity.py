from pathlib import Path


def test_runtime_patch_pauses_other_active_assignments_for_same_account():
    patch = Path("tools/runtime_patch.py").read_text()
    assert "where worker_id in (select id from workers where account_id=%s)" in patch
    assert "status='PAUSED'" in patch
    assert "paused_assignments=cur.fetchall()" in patch
