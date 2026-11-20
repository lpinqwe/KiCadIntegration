"""Поведение гейтов: simulation_model_issue (пункт 4) и lib-check на битой
схеме (пункт 10)."""

import json
from pathlib import Path

from verify import gates
from verify.schemas import GateResult, SEV_ERROR, SEV_WARNING


def _write_pro(project: Path, erc: dict) -> None:
    (project / "design.kicad_pro").write_text(
        json.dumps({"erc": {"rule_severities": erc}}), encoding="utf-8")


def test_sim_model_issue_missing_key_warns(tmp_path: Path):
    _write_pro(tmp_path, {})
    gate = GateResult("erc")
    gates._warn_simulation_model_issue(gate, tmp_path)
    assert any(f.type == "simulation_model_issue_not_error"
               and f.severity == SEV_WARNING for f in gate.findings)


def test_sim_model_issue_ignore_warns(tmp_path: Path):
    _write_pro(tmp_path, {"simulation_model_issue": "ignore"})
    gate = GateResult("erc")
    gates._warn_simulation_model_issue(gate, tmp_path)
    assert any(f.type == "simulation_model_issue_not_error"
               for f in gate.findings)


def test_sim_model_issue_error_no_warning(tmp_path: Path):
    _write_pro(tmp_path, {"simulation_model_issue": "error"})
    gate = GateResult("erc")
    gates._warn_simulation_model_issue(gate, tmp_path)
    assert not gate.findings


def test_lib_check_unparsable_schematic_is_error(tmp_path: Path):
    # hard-гейт не может «пройти», ничего не проверив (пункт 10)
    (tmp_path / "design.kicad_sch").write_text(
        "(kicad_sch (version 20231120)", encoding="utf-8")
    (tmp_path / "index.json").write_text(json.dumps(
        {"requires": ["blk"],
         "blocks": {"blk": {"ports": {"a": {"dir": "in"}}}}}),
        encoding="utf-8")
    gate = gates.gate_lib_check(tmp_path, tmp_path / "design.kicad_sch")
    unavailable = [f for f in gate.findings if f.type == "labels_unavailable"]
    assert unavailable and unavailable[0].severity == SEV_ERROR
    gate.finalize()
    assert gate.status == "fail"


def test_gate_spice_broken_expect_is_finding_not_exception(tmp_path: Path):
    # битый expect.yaml — finding гейта, прогон не рвётся наружу (пункт 3)
    sch = tmp_path / "design.kicad_sch"
    sch.write_text("", encoding="utf-8")
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "expect.yaml").write_text("checks: [unclosed", encoding="utf-8")
    out = tmp_path / "reports"
    out.mkdir()
    gate = gates.gate_spice(sch, out, tmp_path)
    invalid = [f for f in gate.findings if f.type == "expect_invalid"]
    assert invalid and invalid[0].severity == SEV_ERROR


def test_ngspice_timeout_fallback_on_garbage(monkeypatch):
    monkeypatch.setenv("NGSPICE_TIMEOUT", "not-a-number")
    assert gates._ngspice_timeout_s() == gates.DEFAULT_NGSPICE_TIMEOUT_S
    monkeypatch.setenv("NGSPICE_TIMEOUT", "42")
    assert gates._ngspice_timeout_s() == 42
    monkeypatch.delenv("NGSPICE_TIMEOUT")
    assert gates._ngspice_timeout_s() == gates.DEFAULT_NGSPICE_TIMEOUT_S
