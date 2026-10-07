"""Registry of public challenge catalogs for Satoshi Hunt.

Discovery only: every candidate still requires live on-chain verification
before it is eligible for the marketplace.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PublicSource:
    source_id: str
    name: str
    url: str
    asset: str
    source_type: str
    enabled: bool = True


PUBLIC_SOURCES = (
    PublicSource(
        "open-crypto-puzzles",
        "Open Crypto Puzzles",
        "https://raw.githubusercontent.com/floflo777/open-crypto-puzzles/main/puzzles.json",
        "BTC",
        "catalog",
    ),
    PublicSource(
        "crypto-puzzle-atlas",
        "Crypto Puzzle Atlas",
        "https://github.com/itsnex1s/crypto-puzzle-list",
        "BTC",
        "reference",
    ),
    PublicSource(
        "agntn-puzzles",
        "Agntn Public Puzzle Records",
        "https://puzzles.agntn.dev/",
        "BTC",
        "reference",
    ),
)


def sources_for(asset: str = "BTC") -> tuple[PublicSource, ...]:
    asset = asset.upper()
    return tuple(s for s in PUBLIC_SOURCES if s.enabled and s.asset == asset)
