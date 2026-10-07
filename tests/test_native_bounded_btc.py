from challenge_adapters import get_adapter, runtime_contract, runnable_challenge_ids
from challenge_adapters.native_bounded_btc_v1 import digest, verify, solve

def test_native_btc_adapter_is_bounded_and_runnable():
    spec = get_adapter("satoshi-hunt-native-btc-v1")
    assert spec is not None
    assert spec.runnable
    assert spec.execution_mode == "COMPUTE"
    assert "1048575" in (spec.search_space or "")
    assert "satoshi-hunt-native-btc-v1" in runnable_challenge_ids()

def test_native_btc_proof_is_deterministic():
    h = digest("satoshi-hunt-native-btc-v1", 0)
    assert verify("satoshi-hunt-native-btc-v1", 20, 0, h, 1048575)["valid"] is False

def test_native_btc_solver_finds_valid_vector():
    result = solve("satoshi-hunt-native-btc-v1", 8, 100000)
    assert result is not None
    checked = verify("satoshi-hunt-native-btc-v1", 8, result["nonce"], result["hash"], 100000)
    assert checked["valid"] is True

def test_native_btc_runtime_contract():
    contract = runtime_contract("satoshi-hunt-native-btc-v1")
    assert contract["runnable"] is True
    assert contract["adapter_id"] == "native-bounded-btc-v1"
