"""Валидация expect.yaml и block.yaml (пункты ревью 2 и 12)."""

import pytest

from verify.schemas import BlockContract, Check, ConfigError, ExpectConfig


def _check(**overrides):
    base = {"name": "c1", "meas": "m1", "kind": "value",
            "expected": 1.0, "tol_abs": 0.1}
    base.update(overrides)
    return base


def test_check_valid_value():
    check = Check.from_dict(_check())
    assert check.expected == 1.0
    assert check.tol_abs == 0.1


def test_check_valid_inequality_without_tol_abs():
    check = Check.from_dict(_check(kind="inequality", op="<=", tol_abs=None))
    assert check.tol_abs == 0.0
    assert check.op == "<="


def test_check_expected_malformed_string_raises_config_error():
    with pytest.raises(ConfigError, match="expected должен быть числом"):
        Check.from_dict(_check(expected="3.3V"))


def test_check_tol_abs_malformed_raises_config_error():
    with pytest.raises(ConfigError, match="tol_abs должен быть числом"):
        Check.from_dict(_check(tol_abs="wide"))


def test_check_value_without_tol_abs_raises_config_error():
    # Точное float-равенство как молчаливый дефолт — ловушка (пункт 12).
    data = _check()
    del data["tol_abs"]
    with pytest.raises(ConfigError, match="kind=value требует явного tol_abs"):
        Check.from_dict(data)


def test_expect_config_from_dict_valid():
    cfg = ExpectConfig.from_dict({"checks": [_check()]})
    assert len(cfg.checks) == 1


def test_expect_config_empty_checks_raises():
    with pytest.raises(ConfigError, match="checks"):
        ExpectConfig.from_dict({"checks": []})


def test_block_contract_bad_version_raises():
    with pytest.raises(ConfigError, match="version"):
        BlockContract.from_yaml_dict("blk", {"version": "one", "ports": {}})


def test_block_contract_valid():
    contract = BlockContract.from_yaml_dict(
        "blk", {"version": 2, "ports": {"vin": {"dir": "in"}}})
    assert contract.version == 2
    assert "vin" in contract.ports
