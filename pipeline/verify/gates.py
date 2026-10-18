"""Гейты верификации схемы (спека §4: parse, lib-check, erc, datasheet, spice).

Каждый гейт возвращает GateResult с находками; жёсткость (hard/soft) и
итоговый verdict считает вызывающая сторона (__main__.py + finalize).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from . import spice
from .schemas import (
    SEV_ERROR,
    SEV_WARNING,
    STATUS_SKIP,
    BlockContract,
    ConfigError,
    DependencyError,
    GateResult,
    RunError,
)

KICAD_CLI = "kicad-cli"
DEFAULT_HAPPY_ROOT = "/opt/kicad-happy"
ANALYZE_TIMEOUT_S = 120
ERC_TIMEOUT_S = 300
DEFAULT_NGSPICE_TIMEOUT_S = 120
_ERC_SEVERITIES = ("error", "warning", "exclusion")


def _import_skip() -> Any:
    """Импортировать kicad-skip; отсутствие пакета → DependencyError (exit 3)."""
    try:
        import skip
    except ImportError as exc:
        raise DependencyError(
            "kicad-skip не установлен (pip install kicad-skip)") from exc
    return skip


def _skip_parse_errors() -> tuple[type[BaseException], ...]:
    """Исключения sexpdata, которые kicad-skip бросает на битом S-expr."""
    try:
        import sexpdata
    except ImportError:  # pragma: no cover — sexpdata обязателен для kicad-skip
        return ()
    return (sexpdata.ExpectClosingBracket, sexpdata.ExpectNothing,
            sexpdata.ExpectSExp)


def _open_schematic(sch_path: Path) -> tuple[Optional[Any], Optional[str]]:
    """Открыть схему через skip.Schematic; (схема, None) или (None, ошибка)."""
    skip = _import_skip()
    errors = (OSError, ValueError, KeyError, IndexError, TypeError) \
        + _skip_parse_errors()
    try:
        return skip.Schematic(str(sch_path)), None
    except errors as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _rel(path: Path, project_dir: Path) -> str:
    """Путь к артефакту относительно корня проекта (как в report.json §3.4)."""
    return os.path.relpath(path, project_dir)


def _load_yaml_file(path: Path) -> Optional[dict[str, Any]]:
    """Прочитать YAML-файл; ошибка парсинга → None (finding добавляет caller)."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise DependencyError("PyYAML не установлен (pip install PyYAML)") from exc
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------- gate 1: parse

def gate_parse(sch_path: Path, out_dir: Path, project_dir: Path) -> GateResult:
    """Гейт 1 (hard): разбор kicad-skip + анализ kicad-happy (спека §4 #1)."""
    gate = GateResult("parse")
    if not sch_path.is_file():
        gate.add(SEV_ERROR, "file_missing", f"файл схемы не найден: {sch_path}")
        return gate
    _parse_with_skip(gate, sch_path)
    _run_happy_analyzer(gate, sch_path, out_dir)
    return gate


def _parse_with_skip(gate: GateResult, sch_path: Path) -> None:
    """Разобрать .kicad_sch реальным API kicad-skip: skip.Schematic(path)."""
    _, error = _open_schematic(sch_path)
    if error is not None:
        gate.add(SEV_ERROR, "parse_error",
                 f"kicad-skip не смог разобрать схему: {error}")


def _run_happy_analyzer(gate: GateResult, sch_path: Path, out_dir: Path) -> None:
    """Запустить analyze_schematic.py; сбой — warning, не fail (по заданию)."""
    root = Path(os.environ.get("HAPPY_ROOT", DEFAULT_HAPPY_ROOT))
    script = root / "skills" / "kicad" / "analyze_schematic.py"
    if not script.is_file():
        gate.add(SEV_WARNING, "analyzer_missing",
                 f"analyze_schematic.py не найден ({script}), анализ пропущен")
        return
    python = shutil.which("python3") or "python3"
    try:
        proc = subprocess.run([python, str(script), str(sch_path)],
                              capture_output=True, text=True,
                              timeout=ANALYZE_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        gate.add(SEV_WARNING, "analyzer_failed",
                 f"kicad-happy анализ не выполнился: {exc}")
        return
    if proc.returncode != 0:
        gate.add(SEV_WARNING, "analyzer_failed",
                 f"analyze_schematic.py завершился с exit {proc.returncode}")
        return
    _write_analysis_json(gate, out_dir, proc.stdout)


def _write_analysis_json(gate: GateResult, out_dir: Path, stdout: str) -> None:
    """Сохранить stdout анализатора в <out>/analysis.json."""
    out_file = out_dir / "analysis.json"
    try:
        out_file.write_text(stdout, encoding="utf-8")
    except OSError as exc:
        gate.add(SEV_WARNING, "analysis_write_failed",
                 f"не удалось записать {out_file}: {exc}")


# ------------------------------------------------------------- gate 2: lib-check

def gate_lib_check(project_dir: Path, sch_path: Path) -> GateResult:
    """Гейт 2: сверка requires/поротов с index.json; нет индекса → skip (§4 #2)."""
    gate = GateResult("lib-check")
    index_path = project_dir / "index.json"
    if not index_path.is_file():
        gate.status = STATUS_SKIP
        gate.add(SEV_WARNING, "index_missing",
                 "index.json отсутствует — сверка каталога блоков пропущена")
        return gate
    index = _load_index(gate, index_path)
    if index is None:
        return gate
    labels = _collect_global_labels(gate, sch_path)
    blocks = _index_blocks(gate, index)
    requires = _index_requires(gate, index)
    if blocks is None or requires is None or labels is None:
        return gate
    known_ports: set[str] = set()
    for name in requires:
        _check_block(gate, project_dir, name, blocks, labels, known_ports)
    _warn_extra_labels(gate, labels, known_ports)
    return gate


def _load_index(gate: GateResult, index_path: Path) -> Optional[dict[str, Any]]:
    """Прочитать index.json; ошибка парсинга → finding + None."""
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        gate.add(SEV_ERROR, "index_invalid",
                 f"не удалось разобрать index.json: {exc}")
        return None
    if not isinstance(data, dict):
        gate.add(SEV_ERROR, "index_invalid", "index.json: ожидается mapping")
        return None
    return data


def _index_blocks(gate: GateResult,
                  index: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Нормализовать index["blocks"] к виду имя → entry (dict или список)."""
    raw = index.get("blocks") or {}
    if isinstance(raw, dict):
        return {str(k): v for k, v in raw.items()}
    if isinstance(raw, list):
        return {str(b["name"]): b for b in raw if isinstance(b, dict) and "name" in b}
    gate.add(SEV_ERROR, "index_invalid", "index.json: blocks должен быть dict или list")
    return None


def _index_requires(gate: GateResult,
                    index: dict[str, Any]) -> Optional[list[str]]:
    """Прочитать index["requires"] (список имён блоков, которых требует проект)."""
    raw = index.get("requires") or []
    if not isinstance(raw, list):
        gate.add(SEV_ERROR, "index_invalid", "index.json: requires должен быть списком")
        return None
    return [str(name) for name in raw]


def _collect_global_labels(gate: GateResult, sch_path: Path) -> Optional[set[str]]:
    """Имена global label'ов схемы (порты подсхем по спеке §3.1)."""
    sch, error = _open_schematic(sch_path)
    if sch is None:
        gate.add(SEV_WARNING, "labels_unavailable",
                 f"схема не парсится, порты не проверены: {error}")
        return None
    return {str(label.value) for label in sch.global_label}


def _check_block(gate: GateResult, project_dir: Path, name: str,
                 blocks: dict[str, Any], labels: set[str],
                 known_ports: set[str]) -> None:
    """Проверить один обязательный блок: наличие в индексе и порты в схеме."""
    entry = blocks.get(name)
    if entry is None:
        gate.add(SEV_ERROR, "block_missing",
                 f"блок {name!r} из requires отсутствует в index.json")
        return
    contract = _load_contract(gate, project_dir, name, entry)
    if contract is None:
        return
    known_ports.update(contract.ports)
    missing = sorted(p for p in contract.ports if p not in labels)
    if missing:
        gate.add(SEV_ERROR, "port_missing",
                 f"блок {name}: порты {missing} не представлены global label'ами")


def _load_contract(gate: GateResult, project_dir: Path, name: str,
                   entry: Any) -> Optional[BlockContract]:
    """Контракт блока: block.yaml по path из индекса, иначе ports из entry."""
    if not isinstance(entry, dict):
        gate.add(SEV_WARNING, "contract_missing",
                 f"блок {name}: запись индекса не является mapping")
        return None
    yaml_path = _block_yaml_path(project_dir, entry)
    if yaml_path is not None:
        data = _load_yaml_file(yaml_path)
        if data is not None:
            try:
                return BlockContract.from_yaml_dict(name, data)
            except ConfigError as exc:
                gate.add(SEV_ERROR, "contract_invalid", str(exc))
                return None
    ports = entry.get("ports")
    if isinstance(ports, dict):
        return BlockContract(name=name, ports=ports)
    gate.add(SEV_WARNING, "contract_missing",
             f"блок {name}: нет block.yaml и ports в индексе")
    return None


def _block_yaml_path(project_dir: Path, entry: dict[str, Any]) -> Optional[Path]:
    """Путь к block.yaml блока относительно корня проекта."""
    path = entry.get("path")
    if not path:
        return None
    candidate = project_dir / str(path) / "block.yaml"
    return candidate if candidate.is_file() else None


def _warn_extra_labels(gate: GateResult, labels: set[str],
                       known_ports: set[str]) -> None:
    """Global label'ы вне портов обязанных блоков — warning (soft)."""
    extra = sorted(labels - known_ports)
    if extra and known_ports:
        gate.add(SEV_WARNING, "extra_global_label",
                 f"global label'ы вне портов обязанных блоков: {extra}")


# ------------------------------------------------------------------ gate 3: erc

def gate_erc(sch_path: Path, out_dir: Path, project_dir: Path) -> GateResult:
    """Гейт 3: kicad-cli sch erc; error → hard fail, warning → soft (§4 #3).

    Exit 5 от kicad-cli = «есть нарушения» и НЕ является ошибкой запуска.
    """
    gate = GateResult("erc")
    out_json = out_dir / "erc.json"
    rc = _run_erc_cli(sch_path, out_json)
    if out_json.is_file():
        _apply_erc_violations(gate, out_json)
    elif rc == 5:
        gate.add(SEV_ERROR, "erc_report_missing",
                 "kicad-cli сообщил нарушения (exit 5), но erc.json не создан")
    gate.artifact = _rel(out_json, project_dir)
    _warn_simulation_model_issue(gate, project_dir)
    return gate


def _run_erc_cli(sch_path: Path, out_json: Path) -> int:
    """Запустить kicad-cli sch erc (§4.1); неожиданный exit → RunError."""
    cmd = [KICAD_CLI, "sch", "erc", "--format", "json",
           "--severity-error", "--severity-warning", "--exit-code-violations",
           "-o", str(out_json), str(sch_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=ERC_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        raise RunError(f"kicad-cli erc: таймаут {exc.timeout}s") from exc
    except OSError as exc:
        raise DependencyError(f"kicad-cli не запускается: {exc}") from exc
    if proc.returncode not in (0, 5):
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise RunError(
            f"kicad-cli erc: неожиданный exit {proc.returncode}: {tail}")
    return proc.returncode


def _apply_erc_violations(gate: GateResult, out_json: Path) -> None:
    """Разобрать erc.json (sheets[] → violations[]) и наполнить гейт."""
    try:
        data = json.loads(out_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        gate.add(SEV_ERROR, "erc_report_invalid",
                 f"не удалось разобрать erc.json: {exc}")
        return
    counts = dict.fromkeys(_ERC_SEVERITIES, 0)
    for sheet in data.get("sheets", []):
        for viol in sheet.get("violations", []):
            _add_erc_finding(gate, viol, counts)
    gate.summary = counts


def _add_erc_finding(gate: GateResult, viol: dict[str, Any],
                     counts: dict[str, int]) -> None:
    """Одна ERC-нарушение → finding; exclusion считается, но не роняет."""
    severity = str(viol.get("severity", SEV_ERROR)).lower()
    if severity not in _ERC_SEVERITIES:
        severity = SEV_WARNING
    counts[severity] = counts.get(severity, 0) + 1
    if severity == "exclusion":
        return
    gate.add(severity, str(viol.get("type", "erc_violation")),
             str(viol.get("description", "")), _erc_items(viol))


def _erc_items(viol: dict[str, Any]) -> list[dict[str, Any]]:
    """Карта items нарушения к формату report.json §3.4 (pos, uuid)."""
    items = []
    for raw in viol.get("items", []):
        if not isinstance(raw, dict):
            continue
        entry: dict[str, Any] = {"description": raw.get("description", "")}
        if isinstance(raw.get("pos"), dict):
            entry["pos"] = raw["pos"]
        if raw.get("uuid"):
            entry["uuid"] = raw["uuid"]
        items.append(entry)
    return items


def _warn_simulation_model_issue(gate: GateResult, project_dir: Path) -> None:
    """§4.2: simulation_model_issue=ignore в .kicad_pro → warning."""
    data = _load_kicad_pro(project_dir)
    if data is None:
        return
    sev = data.get("erc", {}).get("rule_severities", {})
    if isinstance(sev, dict) and str(sev.get("simulation_model_issue", "")).lower() == "ignore":
        gate.add(SEV_WARNING, "simulation_model_issue_ignored",
                 "simulation_model_issue отключён в ERC (ignore), см. спеку §4.2")


def _load_kicad_pro(project_dir: Path) -> Optional[dict[str, Any]]:
    """Прочитать design.kicad_pro или первый попавшийся *.kicad_pro."""
    preferred = project_dir / "design.kicad_pro"
    candidates = [preferred] if preferred.is_file() \
        else sorted(project_dir.glob("*.kicad_pro"))
    if not candidates:
        return None
    try:
        data = json.loads(candidates[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# -------------------------------------------------------------- gate 4: datasheet

def gate_datasheet(sch_path: Path, project_dir: Path) -> GateResult:
    """Гейт 4 (soft): MPN компонентов против кэша datasheets/extracted (§4 #4)."""
    gate = GateResult("datasheet")
    mpns = _collect_mpns(sch_path)
    if not mpns:
        gate.status = STATUS_SKIP
        gate.add(SEV_WARNING, "no_mpn",
                 "у компонентов не заполнен MPN — проверка даташитов пропущена")
        return gate
    cache_dir = project_dir / "datasheets" / "extracted"
    if not cache_dir.is_dir():
        gate.status = STATUS_SKIP
        gate.add(SEV_WARNING, "cache_missing",
                 f"каталог кэша даташитов не найден: {cache_dir}")
        return gate
    cached = _index_datasheet_cache(cache_dir)
    for ref, mpn in sorted(mpns.items()):
        if mpn.lower() not in cached:
            gate.add(SEV_WARNING, "datasheet_missing",
                     f"{ref} ({mpn}): нет записи в datasheets/extracted")
    return gate


def _collect_mpns(sch_path: Path) -> dict[str, str]:
    """Собрать свойства MPN: reference → mpn через kicad-skip."""
    sch, _error = _open_schematic(sch_path)
    if sch is None:
        return {}
    mpns: dict[str, str] = {}
    for symbol in sch.symbol:
        try:
            mpn = str(symbol.property.MPN.value).strip()
            ref = str(symbol.property.Reference.value)
        except AttributeError:
            continue  # у символа нет свойства MPN
        if mpn:
            mpns[ref] = mpn
    return mpns


def _index_datasheet_cache(cache_dir: Path) -> set[str]:
    """Индекс кэша: множество MPN (имя файла без расширения + поле mpn)."""
    cached: set[str] = set()
    for path in sorted(cache_dir.glob("*.json")):
        cached.add(path.stem.lower())
        cached.update(_mpn_fields_from_json(path))
    return cached


def _mpn_fields_from_json(path: Path) -> set[str]:
    """MPN-поля из JSON-записи кэша (если файл читается как mapping)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    out = set()
    for key in ("mpn", "MPN", "part_number"):
        if isinstance(data.get(key), str):
            out.add(data[key].lower())
    return out


# ----------------------------------------------------------------- gate 5: spice

def gate_spice(sch_path: Path, out_dir: Path, project_dir: Path) -> GateResult:
    """Гейт 5 (hard): netlist → ngspice → .meas против expect.yaml (§4 #5).

    Нет bench/expect.yaml → status skip (НЕ fail). Exit code ngspice как
    признак успеха не используется — только наличие строк .meas в логе.
    """
    gate = GateResult("spice")
    expect_path = spice.find_expect(sch_path)
    if expect_path is None:
        gate.status = STATUS_SKIP
        gate.add(SEV_WARNING, "no_testbench",
                 "bench/expect.yaml не найден — SPICE-проверка пропущена")
        return gate
    expect = spice.load_expect(expect_path)
    net_path = out_dir / "circuit.net"
    ok, message = spice.export_netlist(KICAD_CLI, sch_path, net_path)
    if not ok:
        gate.add(SEV_ERROR, "netlist_export_failed", message)
        return gate
    values = _simulate(gate, net_path, out_dir)
    cases = _apply_checks(gate, expect.checks, values)
    _write_sim_report(out_dir, gate, cases)
    gate.artifact = _rel(out_dir / "sim.json", project_dir)
    return gate


def _simulate(gate: GateResult, net_path: Path,
              out_dir: Path) -> dict[str, float]:
    """Прогнать ngspice и вернуть .meas-значения из лога."""
    timeout = int(os.environ.get("NGSPICE_TIMEOUT", DEFAULT_NGSPICE_TIMEOUT_S))
    log_path = out_dir / "circuit.log"
    try:
        spice.run_ngspice(net_path, out_dir / "circuit.raw", log_path, timeout)
    except subprocess.TimeoutExpired as exc:
        gate.add(SEV_ERROR, "ngspice_timeout",
                 f"ngspice превысил таймаут {exc.timeout}s")
        return {}
    return spice.parse_meas_values(spice.read_log(log_path))


def _apply_checks(gate: GateResult, checks: list[Any],
                  values: dict[str, float]) -> list[dict[str, Any]]:
    """Сверить каждый check; hard → error, soft → warning. Возвращает cases."""
    cases: list[dict[str, Any]] = []
    passed = failed = 0
    for check in checks:
        result = spice.evaluate_check(check, values)
        actual = values.get(check.meas.lower())
        case = {"name": check.name, "meas": check.meas, "value": actual,
                "expected": check.expected, "result": "pass"}
        if result is None:
            case["result"] = "missing"
            _add_check_finding(gate, check, actual,
                               f".meas {check.meas!r} не найден в выводе ngspice")
            failed += 1
        elif not result:
            case["result"] = "fail"
            op_str = f"{check.op} " if check.op else ""
            _add_check_finding(
                gate, check, actual,
                f"{check.meas}={actual} не проходит {check.kind} "
                f"{op_str}{check.expected}{check.unit}")
            failed += 1
        else:
            passed += 1
        cases.append(case)
    gate.summary = {"checked": len(checks), "passed": passed, "failed": failed}
    return cases


def _add_check_finding(gate: GateResult, check: Any,
                       actual: Optional[float], detail: str) -> None:
    """Finding для проваленного/отсутствующего check с учётом hard/soft."""
    severity = SEV_ERROR if spice.is_hard(check) else SEV_WARNING
    gate.add(severity, "check_failed",
             f"check {check.name} ({check.severity}): {detail}")


def _write_sim_report(out_dir: Path, gate: GateResult,
                      cases: list[dict[str, Any]]) -> None:
    """Записать <out>/sim.json — детализация гейта spice (артефакт §3.4)."""
    payload = {"gate": "spice", "summary": gate.summary or {}, "cases": cases}
    try:
        (out_dir / "sim.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    except OSError as exc:
        gate.add(SEV_WARNING, "sim_write_failed",
                 f"не удалось записать sim.json: {exc}")
