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
