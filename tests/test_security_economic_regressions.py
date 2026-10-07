import ast
from pathlib import Path

from payouts import finalize_external_payout


API_SOURCE = Path("backend/api.py").read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    tree = ast.parse(API_SOURCE)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(API_SOURCE, node) or ""
    raise AssertionError(f"function not found: {name}")


def test_admin_withdrawal_completion_cannot_skip_processing():
    source = _function_source("complete_withdrawal")
    assert "status='PROCESSING'" in source
    assert "status in ('QUEUED','PROCESSING')" not in source


def test_approved_rewards_cannot_be_voided_after_credit():
    source = _function_source("void_reward")
    assert "settlement_status='REVIEW'" in source
    assert "settlement_status in ('REVIEW','APPROVED')" not in source


def test_ingestion_requires_runnable_bounded_deterministic_compute():
    source = _function_source("ingest_challenge")
    assert "execution_mode" in source
    assert "adapter_runnable" in source
    assert "bounded_search_space" in source
    assert "deterministic_verifier" in source


def test_job_reads_are_account_scoped():
    list_source = _function_source("list_jobs")
    get_source = _function_source("get_job")
    assert "w.account_id=%s" in list_source
    assert "w.account_id=%s" in get_source


def test_payout_finalization_requires_processing():
    request = {"status": "QUEUED"}
    try:
        finalize_external_payout(request, "a" * 64)
    except ValueError as exc:
        assert "PROCESSING" in str(exc)
    else:
        raise AssertionError("QUEUED payout must not finalize")
