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
