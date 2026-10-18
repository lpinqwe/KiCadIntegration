"""Датаклассы и типы данных verify-пайплайна (без pydantic, только stdlib).

Контракт: docs/specs/2026-10-07-kicad-agent-pipeline-v1.md, §3.3 (expect.yaml),
§3.4 (report.json), §4 (гейты).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Optional

# Статусы гейтов и уровни жёсткости (спека §4)
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_SKIP = "skip"

SEV_ERROR = "error"
SEV_WARNING = "warning"

SEVERITY_HARD = "hard"
SEVERITY_SOFT = "soft"

VALID_GATE_STATUSES = (STATUS_PASS, STATUS_FAIL, STATUS_SKIP)


def eprint(*args: Any, **kwargs: Any) -> None:
    """Печать в stderr (в stdout по правилам пайплайна ничего не пишем)."""
    kwargs.setdefault("file", sys.stderr)
    print(*args, **kwargs)


class VerifyError(Exception):
    """Базовая ошибка verify; атрибут code — exit code CLI."""

    code: int = 2

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        """Создать ошибку с сообщением и (опционально) переопределённым code."""
        super().__init__(message)
        if code is not None:
            self.code = code


class ConfigError(VerifyError):
    """Ошибка конфигурации запуска (нет схемы, неверные аргументы) → exit 2."""

    code = 2


class RunError(VerifyError):
    """Ошибка запуска внешней утилиты (неожиданный exit code kicad-cli) → exit 2."""

    code = 2


class DependencyError(VerifyError):
    """Не найдена зависимость (kicad-cli/ngspice/kicad-skip/PyYAML) → exit 3."""

    code = 3


@dataclass
class Finding:
    """Отдельная находка гейта (элемент списка errors в report.json)."""

    gate: str
    severity: str
    type: str
    message: str
    items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в dict для report.json (§3.4)."""
        return {
            "gate": self.gate,
            "severity": self.severity,
            "type": self.type,
            "message": self.message,
            "items": self.items,
        }


@dataclass
class GateResult:
    """Результат одного гейта: статус, находки, артефакт, summary."""

    name: str
    status: str = STATUS_PASS
    findings: list[Finding] = field(default_factory=list)
    artifact: Optional[str] = None
    summary: Optional[dict[str, int]] = None

    def add(self, severity: str, type_: str, message: str,
            items: Optional[list[dict[str, Any]]] = None) -> None:
        """Добавить находку к результату гейта."""
        self.findings.append(Finding(self.name, severity, type_, message, items or []))

    def finalize(self, strict: bool = False) -> None:
        """Пересчитать статус по находкам; strict включает warning'и в fail.

        Гейт со статусом skip не пересчитывается (спека §4: пропуск ≠ провал).
        """
        if self.status == STATUS_SKIP:
            return
        failed = any(f.severity == SEV_ERROR for f in self.findings)
        if strict:
            failed = failed or any(
                f.severity == SEV_WARNING for f in self.findings)
        self.status = STATUS_FAIL if failed else STATUS_PASS

    def to_dict(self) -> dict[str, Any]:
        """Сериализация гейта для report.json (§3.4)."""
        out: dict[str, Any] = {
            "status": self.status,
            "errors": [f.to_dict() for f in self.findings
                       if f.severity == SEV_ERROR],
        }
        if self.artifact is not None:
            out["artifact"] = self.artifact
        if self.summary is not None:
            out["summary"] = self.summary
        return out


@dataclass
class Check:
    """Один check из expect.yaml (спека §3.3)."""

    name: str
    meas: str
    kind: str  # value | inequality
    expected: float
    op: Optional[str] = None  # только для inequality: <=, <, >=, >, ==, !=
    tol_abs: float = 0.0
    unit: str = ""
    severity: str = SEVERITY_HARD

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Check":
        """Разобрать запись checks[] из expect.yaml с валидацией полей."""
        kind = str(data.get("kind", ""))
        if kind not in ("value", "inequality"):
            raise ConfigError(f"check {data.get('name')!r}: kind must be "
                              f"'value' or 'inequality', got {kind!r}")
        if "expected" not in data:
            raise ConfigError(f"check {data.get('name')!r}: поле expected отсутствует")
        op = data.get("op")
        if kind == "inequality" and op not in ("<=", "<", ">=", ">", "==", "!="):
            raise ConfigError(f"check {data.get('name')!r}: "
                              f"недопустимый op {op!r} для inequality")
        return cls(
            name=str(data.get("name", "")),
            meas=str(data.get("meas", data.get("name", ""))),
            kind=kind,
            expected=float(data["expected"]),
            op=str(op) if op is not None else None,
            tol_abs=float(data.get("tol_abs", 0.0)),
            unit=str(data.get("unit", "")),
            severity=str(data.get("severity", SEVERITY_HARD)),
        )


@dataclass
class ExpectConfig:
    """Содержимое bench/expect.yaml (спека §3.3)."""

    analysis: list[dict[str, Any]] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExpectConfig":
        """Разобрать корень expect.yaml; checks обязателен и должен быть списком."""
        raw_checks = data.get("checks")
        if not isinstance(raw_checks, list) or not raw_checks:
            raise ConfigError("expect.yaml: checks должен быть непустым списком")
        return cls(
            analysis=list(data.get("analysis") or []),
            checks=[Check.from_dict(c) for c in raw_checks],
        )


@dataclass
class BlockContract:
    """Интерфейс блока каталога из block.yaml (спека §3.2, для lib-check)."""

    name: str
    ports: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    requires: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml_dict(cls, name: str, data: dict[str, Any]) -> "BlockContract":
        """Разобрать block.yaml; ports — dict имя → описание порта."""
        ports = data.get("ports") or {}
        if not isinstance(ports, dict):
            raise ConfigError(f"block.yaml {name!r}: ports должен быть mapping")
        return cls(
            name=name,
            ports=ports,
            version=int(data.get("version", 1)),
            requires=list(data.get("requires") or []),
        )


@dataclass
class Report:
    """Корень report.json (спека §3.4)."""

    schema: str = "kicad-agent/report.v1"
    project: str = ""
    revision: str = "unknown"
    timestamp: str = ""
    kicad_version: str = "unknown"
    gates: dict[str, GateResult] = field(default_factory=dict)
    verdict: str = STATUS_PASS
    errors: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в dict строго по форме §3.4."""
        return {
            "schema": self.schema,
            "project": self.project,
            "revision": self.revision,
            "timestamp": self.timestamp,
            "kicad_version": self.kicad_version,
            "gates": {name: g.to_dict() for name, g in self.gates.items()},
            "verdict": self.verdict,
            "errors": [f.to_dict() for f in self.errors],
        }
