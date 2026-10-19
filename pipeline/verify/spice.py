"""SPICE-часть verify: netlist, ngspice, разбор .meas, сверка с expect.yaml.

Контракт: спека §3.3 (expect.yaml) и §4.1 (правила запуска ngspice).
Exit code ngspice не используется как признак успеха — только наличие
строк .meas в логе (ngspice возвращает ненадёжные коды).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from .schemas import Check, ConfigError, DependencyError, ExpectConfig

# Имя файла ожиданий рядом со схемой: <sch_dir>/bench/expect.yaml
EXPECT_FILENAME = Path("bench") / "expect.yaml"

# Строка вывода ngspice с результатом .meas: "vout_nom = 3.298000e+00"
_MEAS_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
    r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*$"
)


def find_expect(sch_path: Path) -> Optional[Path]:
    """Найти bench/expect.yaml рядом со схемой; None, если тестбенча нет."""
    candidate = sch_path.parent / EXPECT_FILENAME
    return candidate if candidate.is_file() else None


def load_expect(path: Path) -> ExpectConfig:
    """Распарсить expect.yaml (формат спеки §3.3). Ошибки → ConfigError."""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on окружение
        raise ConfigError("PyYAML не установлен: pip install PyYAML") from exc
    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except OSError as exc:
        raise ConfigError(f"не удалось прочитать {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"некорректный YAML в {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: ожидается mapping в корне")
    return ExpectConfig.from_dict(data)


def export_netlist(kicad_cli: str, sch_path: Path, out_net: Path) -> tuple[bool, str]:
    """Экспорт SPICE-netlist через kicad-cli (§4.1).

    Возвращает (ok, message); при ok=False message содержит stderr для отчёта.
    """
    cmd = [kicad_cli, "sch", "export", "netlist", "--format", "spice",
           "-o", str(out_net), str(sch_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"запуск kicad-cli не удался: {exc}"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-500:]
        return False, f"kicad-cli export netlist: exit {proc.returncode}: {tail}"
    return True, ""


def run_ngspice(net_path: Path, raw_path: Path, log_path: Path,
                timeout: int) -> tuple[int, str]:
    """Прогнать ngspice -b (§4.1). Возвращает (returncode, stderr).

    TimeoutExpired пробрасывается наверх — вызывающий превращает его
    в finding гейта spice.
    """
    cmd = ["ngspice", "-b", "-r", str(raw_path), "-o", str(log_path),
           str(net_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout)
    except OSError as exc:
        # Отсутствие бинаря ngspice — exit 3 по контракту __main__.py.
        raise DependencyError(f"не удалось запустить ngspice: {exc}") from exc
    return proc.returncode, (proc.stderr or "").strip()


def parse_meas_values(log_text: str) -> dict[str, float]:
    """Собрать результаты .meas из текста лога ngspice: имя → значение."""
    values: dict[str, float] = {}
    for line in log_text.splitlines():
        match = _MEAS_RE.match(line)
        if match:
            values[match.group(1).lower()] = float(match.group(2))
    return values


def read_log(log_path: Path) -> str:
    """Прочитать лог ngspice; отсутствие файла — пустая строка."""
    try:
        return log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _compare_value(check: Check, actual: float) -> bool:
    """Проверка kind=value: |actual - expected| <= tol_abs."""
    return abs(actual - check.expected) <= check.tol_abs


def _compare_inequality(check: Check, actual: float) -> bool:
    """Проверка kind=inequality по оператору op."""
    ops = {
        "<=": lambda a, e: a <= e,
        "<": lambda a, e: a < e,
        ">=": lambda a, e: a >= e,
        ">": lambda a, e: a > e,
        "==": lambda a, e: a == e,
        "!=": lambda a, e: a != e,
    }
    func = ops.get(check.op or "")
    if func is None:
        return False
    return func(actual, check.expected)


def evaluate_check(check: Check, values: dict[str, float]) -> Optional[bool]:
    """Сверить один check с найденными .meas-значениями.

    Возвращает True/False или None, если .meas в выводе отсутствует.
    """
    actual = values.get(check.meas.lower())
    if actual is None:
        return None
    if check.kind == "value":
        return _compare_value(check, actual)
    return _compare_inequality(check, actual)


def is_hard(check: Check) -> bool:
    """Проверка относится к hard-уровню (по умолчанию hard)."""
    return check.severity != "soft"
