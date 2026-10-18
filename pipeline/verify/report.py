"""Формирование report.json и report.md (контракт спеки §3.4)."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .schemas import (
    SEV_ERROR,
    SEV_WARNING,
    STATUS_FAIL,
    STATUS_SKIP,
    Finding,
    GateResult,
    Report,
)

REPORT_SCHEMA = "kicad-agent/report.v1"
_GATE_ORDER = ("parse", "lib-check", "erc", "datasheet", "spice")
_STATUS_ICON = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}


def get_revision(project_dir: Path) -> str:
    """Краткий git-sha корня проекта; иначе 'unknown' (§3.4)."""
    try:
        proc = subprocess.run(["git", "-C", str(project_dir), "rev-parse",
                               "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    sha = proc.stdout.strip()
    return sha if proc.returncode == 0 and sha else "unknown"


def get_kicad_version(kicad_cli: str = "kicad-cli") -> str:
    """Версия kicad-cli (`kicad-cli version`); иначе 'unknown' (§3.4)."""
    if shutil.which(kicad_cli) is None:
        return "unknown"
    try:
        proc = subprocess.run([kicad_cli, "version"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    version = proc.stdout.strip().splitlines()
    return version[0].strip() if proc.returncode == 0 and version else "unknown"


def _utc_timestamp() -> str:
    """Метка времени ISO-8601 в UTC (вид 2026-10-07T12:00:00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_report(project_dir: Path, gates: dict[str, GateResult],
                 kicad_version: str, revision: str) -> Report:
    """Собрать Report: verdict fail, если хотя бы один гейт в status fail."""
    ordered = {name: gates[name] for name in _GATE_ORDER if name in gates}
    verdict = STATUS_FAIL if any(
        g.status == STATUS_FAIL for g in ordered.values()) else "pass"
    return Report(
        schema=REPORT_SCHEMA,
        project=project_dir.name,
        revision=revision,
        timestamp=_utc_timestamp(),
        kicad_version=kicad_version,
        gates=ordered,
        verdict=verdict,
        errors=_collect_findings(ordered),
    )


def _collect_findings(gates: dict[str, GateResult]) -> list[Finding]:
    """Собрать все находки всех гейтов (errors и warnings) в плоский список."""
    findings: list[Finding] = []
    for gate in gates.values():
        findings.extend(gate.findings)
    return findings


def render_markdown(report: Report) -> str:
    """Отчёт report.md: таблица гейтов + список ошибок (§3.4)."""
    lines = [f"# Verify report — {report.project}", "",
             f"- revision: `{report.revision}`",
             f"- kicad: `{report.kicad_version}`",
             f"- timestamp: `{report.timestamp}`",
             f"- verdict: **{report.verdict.upper()}**", "",
             "| Gate | Status |", "|---|---|"]
    for name, gate in report.gates.items():
        lines.append(f"| {name} | {_STATUS_ICON.get(gate.status, gate.status)} |")
    lines.extend(_markdown_findings(report.errors))
    return "\n".join(lines) + "\n"


def _markdown_findings(findings: list[Finding]) -> list[str]:
    """Блок «Ошибки» markdown-отчёта; пусто — заголовок без строк."""
    lines = ["", "## Ошибки", ""]
    if not findings:
        lines.append("Замечаний нет.")
        return lines
    lines.append("| Тип | Уровень | Позиция | Сообщение |")
    lines.append("|---|---|---|---|")
    for finding in findings:
        lines.append("| {} | {} | {} | {} |".format(
            finding.type, finding.severity,
            _positions(finding.items), _escape(finding.message)))
    return lines


def _positions(items: list[dict]) -> str:
    """Позиции элементов находки: 'ref@(x,y); ...'."""
    parts = []
    for item in items:
        pos = item.get("pos") or {}
        coord = f"({pos['x']},{pos['y']})" if "x" in pos and "y" in pos else ""
        label = item.get("description") or item.get("ref") or item.get("uuid") or "?"
        parts.append(f"{label}{coord}")
    return "; ".join(parts)


def _escape(text: str) -> str:
    """Экранировать '|' и переводы строк для markdown-таблицы."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def write_reports(report: Report, out_dir: Path, fmt: str) -> list[Path]:
    """Записать report.json и/или report.md по --format json|md|both."""
    written: list[Path] = []
    if fmt in ("json", "both"):
        path = out_dir / "report.json"
        path.write_text(json.dumps(report.to_dict(), ensure_ascii=False,
                                   indent=2) + "\n", encoding="utf-8")
        written.append(path)
    if fmt in ("md", "both"):
        path = out_dir / "report.md"
        path.write_text(render_markdown(report), encoding="utf-8")
        written.append(path)
    return written


def gate_error_findings(gate: GateResult) -> list[Finding]:
    """Находки гейта с severity=error (для логирования)."""
    return [f for f in gate.findings if f.severity == SEV_ERROR]


def gate_warning_findings(gate: GateResult) -> list[Finding]:
    """Находки гейта с severity=warning (для логирования)."""
    return [f for f in gate.findings if f.severity == SEV_WARNING]


def skipped_gates(gates: dict[str, GateResult]) -> list[str]:
    """Имена гейтов со статусом skip."""
    return [name for name, g in gates.items() if g.status == STATUS_SKIP]
