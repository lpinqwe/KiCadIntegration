"""_load_yaml_file / _load_contract: файла нет vs файл битый (пункт ревью 1)."""

from pathlib import Path

import pytest

from verify import gates
from verify.schemas import ConfigError, GateResult


def test_load_yaml_file_missing_returns_none(tmp_path: Path):
    assert gates._load_yaml_file(tmp_path / "nope.yaml") is None


def test_load_yaml_file_broken_yaml_raises_config_error(tmp_path: Path):
    path = tmp_path / "block.yaml"
    path.write_text("ports: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="некорректный YAML"):
        gates._load_yaml_file(path)


def test_load_yaml_file_non_mapping_raises_config_error(tmp_path: Path):
    path = tmp_path / "block.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="mapping"):
        gates._load_yaml_file(path)


def test_load_yaml_file_valid(tmp_path: Path):
    path = tmp_path / "block.yaml"
    path.write_text("ports:\n  vin: {dir: in}\n", encoding="utf-8")
    assert gates._load_yaml_file(path) == {"ports": {"vin": {"dir": "in"}}}


def test_load_contract_missing_block_yaml_falls_back_to_ports(tmp_path: Path):
    gate = GateResult("lib-check")
    entry = {"path": "lib/power/ldo", "ports": {"vin": {"dir": "in"}}}
    contract = gates._load_contract(gate, tmp_path, "ldo", entry)
    assert contract is not None
    assert "vin" in contract.ports
    assert not any(f.type == "contract_invalid" for f in gate.findings)


def test_load_contract_broken_block_yaml_emits_contract_invalid(tmp_path: Path):
    gate = GateResult("lib-check")
    block_dir = tmp_path / "lib" / "power" / "ldo"
    block_dir.mkdir(parents=True)
    (block_dir / "block.yaml").write_text("ports: [unclosed", encoding="utf-8")
    entry = {"path": "lib/power/ldo", "ports": {"vin": {"dir": "in"}}}
    contract = gates._load_contract(gate, tmp_path, "ldo", entry)
    assert contract is None
    invalid = [f for f in gate.findings if f.type == "contract_invalid"]
    assert invalid and invalid[0].severity == "error"


def test_load_contract_valid_block_yaml(tmp_path: Path):
    gate = GateResult("lib-check")
    block_dir = tmp_path / "lib" / "power" / "ldo"
    block_dir.mkdir(parents=True)
    (block_dir / "block.yaml").write_text(
        "version: 1\nports:\n  vin: {dir: in}\n  gnd: {dir: power}\n",
        encoding="utf-8")
    entry = {"path": "lib/power/ldo"}
    contract = gates._load_contract(gate, tmp_path, "ldo", entry)
    assert contract is not None
    assert set(contract.ports) == {"vin", "gnd"}
    assert not gate.findings
