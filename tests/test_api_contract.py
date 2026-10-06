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
