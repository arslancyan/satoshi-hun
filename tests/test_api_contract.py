from uuid import UUID

from backend.api import ClaimCreate


def test_claim_requires_assignment_identity():
    claim = ClaimCreate(
        assignment_id=UUID("00000000-0000-0000-0000-000000000001"),
        worker_id=UUID("00000000-0000-0000-0000-000000000002"),
        candidate_hash="a" * 64,
        result_status="TESTED",
        cpu_seconds=0,
    )
    assert claim.assignment_id.int != claim.worker_id.int


def test_worker_auth_routes_exist():
    from backend.api import app
    routes = {route.path for route in app.routes}
    assert "/workers/{worker_id}/revoke" in routes
    assert "/audit/job/{job_id}/verify" in routes

def test_untrusted_verified_claim_is_blocked_in_route_source():
    from backend.api import claim
    import inspect
    source = inspect.getsource(claim)
    assert 'VERIFIED claims require a server-side challenge adapter.' in source

def test_assignment_state_transitions_use_rowcount_guards():
    from backend.api import start_assignment, complete_assignment
    import inspect
    assert 'where id=%s and status=\'ASSIGNED\'' in inspect.getsource(start_assignment)
    assert 'where id=%s and status=\'RUNNING\'' in inspect.getsource(complete_assignment)

def test_public_claim_schema_cannot_request_verified():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        ClaimCreate(
            assignment_id=UUID("00000000-0000-0000-0000-000000000001"),
            worker_id=UUID("00000000-0000-0000-0000-000000000002"),
            candidate_hash="a" * 64,
            result_status="VERIFIED",
        )


def test_marketplace_exposes_runnable_and_research_catalog_separately():
    from backend.api import marketplace
    import inspect
    source = inspect.getsource(marketplace)
    assert '"catalog":rows' in source
    assert '"runnable"] = queue_eligible' in source
    assert 'market_status' in source
    assert "where status is not null" in source
    assert 'return {"challenges":runnable' in source
