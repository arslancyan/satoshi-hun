import importlib


def test_legacy_registry_and_adapter_package_can_coexist():
    registry = importlib.import_module("challenge_adapters")
    adapter = importlib.import_module("challenge_adapters.peter_todd_hash_collision")

    assert hasattr(registry, "runtime_contract")
    assert adapter.ADAPTER.challenge_type == "hash-collision"
