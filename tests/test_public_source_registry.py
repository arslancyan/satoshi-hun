from public_source_registry import sources_for


def test_btc_sources_are_enabled_and_unique():
    sources = sources_for("btc")
    assert len(sources) >= 2
    ids = [source.source_id for source in sources]
    assert len(ids) == len(set(ids))
    assert all(source.asset == "BTC" for source in sources)
