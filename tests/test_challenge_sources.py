from challenge_sources import _parse_expected_sats, _published_reward_sats

def test_parse_expected_btc_and_sats():
    assert _parse_expected_sats("1.00016775 BTC") == 100016775
    assert _parse_expected_sats("20107284 sats") == 20107284

def test_published_reward_supports_btc():
    assert _published_reward_sats({"prize":{"amount":1.2563451,"asset":"BTC"}}) == 125634510

def test_published_reward_supports_sats():
    assert _published_reward_sats({"prize":{"amount":20107284,"asset":"sats"}}) == 20107284
