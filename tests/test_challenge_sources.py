from challenge_sources import _parse_expected_sats, _published_reward_sats

def test_parse_expected_btc_and_sats():
    assert _parse_expected_sats("1.00016775 BTC") == 100016775
    assert _parse_expected_sats("20107284 sats") == 20107284

def test_published_reward_supports_btc():
    assert _published_reward_sats({"prize":{"amount":1.2563451,"asset":"BTC"}}) == 125634510

def test_published_reward_supports_sats():
    assert _published_reward_sats({"prize":{"amount":20107284,"asset":"sats"}}) == 20107284

from challenge_sources import _counts_toward_prize

def test_non_prize_escrow_is_excluded():
    assert not _counts_toward_prize({"label":"creator controlled; not counted as prize"})

def test_live_prize_escrow_is_counted():
    assert _counts_toward_prize({"label":"main", "expected":"1 BTC"})

from challenge_sources import ID_ALIASES, AUTHORITATIVE_ESCROW_SPEND_SLUGS

def test_stable_id_alias_prevents_catalog_rename():
    assert ID_ALIASES["peter-todd-hash-collision-bounties-0-59btc"] == "peter-todd-hash-collision-bounties"

def test_authoritative_solve_rule_is_explicit():
    assert "peter-todd-hash-collision-bounties-0-59btc" in AUTHORITATIVE_ESCROW_SPEND_SLUGS

def test_live_record_exports_search_metrics():
    from challenge_sources import LiveSourceRecord
    record = LiveSourceRecord(
        "demo", "Demo", "bitcoin", 1.0, 1.0, "OPEN + FUNDED",
        {"url": "https://example.com", "source_id": "demo", "checked_at": "2026-01-01T00:00:00Z"},
        {"method": "test", "source_id": "demo", "checked_at": "2026-01-01T00:00:00Z", "fingerprint": "x"},
        {"permissionless": False}, [], "research", "test",
        {"keyspace_total": "1024", "keyspace_remaining": "1024", "difficulty_category": "EXTREME"},
    )
    assert record.as_registry()["search_metrics"]["keyspace_total"] == "1024"


def test_live_sync_uses_runtime_discovery_readiness():
    from challenge_sources import adapter_readiness
    runnable = adapter_readiness("peter-todd-sha256-bounty")
    research = adapter_readiness("keir-finlow-bates-blockchain-book-600ksats")
    unknown = adapter_readiness("future-source-puzzle")
    assert runnable["readiness"] == "VERIFIED"
    assert runnable["execution_allowed"] is True
    assert research["readiness"] == "VERIFIED"
    assert research["execution_allowed"] is False
    assert unknown["readiness"] == "DISCOVERED"
    assert unknown["execution_allowed"] is False
