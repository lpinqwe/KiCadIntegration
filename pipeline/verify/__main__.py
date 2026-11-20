"""Точка входа CLI verify: argparse, запуск гейтов, отчёт, exit codes.

Exit codes: 0 = pass, 1 = fail, 2 = ошибка запуска/конфигурации,
3 = нет зависимости (kicad-cli/ngspice/kicad-skip/PyYAML).
"""

from __future__ import annotations

import argparse
import shutil
import sys
import traceback
from pathlib import Path
from typing import Optional, Sequence

if __package__ in (None, ""):
    # Прямой запуск файла (`python3 .../verify/__main__.py`, как в Dockerfile):
    # кладём родительский каталог на sys.path и трактуем модуль как пакет verify.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "verify"

from . import report, spice
from . import gates as gate_mod
from .schemas import (
    ConfigError,
    DependencyError,
    GateResult,
    VerifyError,
    eprint,
)

GATE_NAMES = ("parse", "lib-check", "erc", "datasheet", "spice")

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CONFIG = 2
EXIT_DEPS = 3


def build_parser() -> argparse.ArgumentParser:
    """Описать CLI: verify [--project DIR] [--sch FILE] [--out DIR] ..."""
    parser = argparse.ArgumentParser(
        prog="verify",
        description="Гейты верификации схемы KiCad (спека §4)")
    parser.add_argument("--project", default=".", metavar="DIR",
                        help="корень проекта (по умолчанию cwd)")
    parser.add_argument("--sch", metavar="FILE",
                        help="файл .kicad_sch (иначе ищется в корне проекта)")
    parser.add_argument("--out", metavar="DIR",
                        help="каталог отчётов (по умолчанию <project>/reports)")
    parser.add_argument("--only", metavar="G1,G2",
                        help="только перечисленные гейты: " + ", ".join(GATE_NAMES))
    parser.add_argument("--format", choices=("json", "md", "both"), default="both",
                        help="формат отчёта (по умолчанию both)")
    parser.add_argument("--strict", action="store_true",
                        help="warning'и и soft-гейты тоже роняют")
    return parser


def resolve_schematic(project: Path, sch_arg: Optional[str]) -> Path:
    """Найти .kicad_sch: файл из --sch или ровно один в корне проекта."""
    if sch_arg:
        path = Path(sch_arg)
        if not path.is_absolute():
            path = project / path
        if not path.is_file():
            raise ConfigError(f"файл схемы не найден: {path}")
        return path.resolve()
    candidates = sorted(project.glob("*.kicad_sch"))
    if not candidates:
        raise ConfigError(f"в {project} нет файлов *.kicad_sch; укажите --sch")
    if len(candidates) > 1:
        names = ", ".join(c.name for c in candidates)
        raise ConfigError(
            f"в корне проекта несколько схем ({names}) — укажите --sch FILE")
    return candidates[0].resolve()


def select_gates(only: Optional[str]) -> list[str]:
    """Разобрать --only в канонический порядок; неизвестное имя → ConfigError."""
    if not only:
        return list(GATE_NAMES)
    selected = {name.strip() for name in only.split(",") if name.strip()}
    unknown = sorted(selected - set(GATE_NAMES))
    if unknown:
        raise ConfigError(f"неизвестные гейты в --only: {unknown}; "
                          f"доступны: {', '.join(GATE_NAMES)}")
    return [name for name in GATE_NAMES if name in selected]


def ensure_out_dir(out: Path) -> None:
    """Создать каталог отчётов; отказ файловой системы → ConfigError."""
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(
            f"не удалось создать каталог отчётов {out}: {exc}") from exc


def _require_module(module: str, package: str) -> None:
    """Проверить, что Python-пакет импортируется; отсутствие → exit 3."""
    try:
        __import__(module)
    except ImportError as exc:
        raise DependencyError(f"{package} не установлен ({exc})") from exc


def check_dependencies(selected: Sequence[str]) -> None:
    """Проверить kicad-cli и Python-пакеты; отсутствие → DependencyError (exit 3).

    Зависимости, не зависящие от проекта (бинарь kicad-cli, пакеты), проверяются
    до резолва путей — отсутствие окружения важнее ошибки пути проекта.
    """
    names = set(selected)
    if names & {"erc", "spice"} and shutil.which("kicad-cli") is None:
        raise DependencyError("kicad-cli не найден в PATH (нужен гейтам erc/spice)")
    if names & {"parse", "lib-check", "datasheet"}:
        _require_module("skip", "kicad-skip")
    if "spice" in names:
        _require_module("yaml", "PyYAML")


def check_ngspice_dependency(selected: Sequence[str], sch: Path) -> None:
    """ngspice нужен только при наличии bench/expect.yaml; нет → exit 3."""
    if "spice" in set(selected) and spice.find_expect(sch) is not None \
            and shutil.which("ngspice") is None:
        raise DependencyError("ngspice не найден в PATH (нужен для гейта spice)")


def run_gates(selected: Sequence[str], sch: Path, out: Path,
              project: Path) -> dict[str, GateResult]:
    """Выполнить выбранные гейты в каноническом порядке (спека §4)."""
    runners = {
        "parse": lambda: gate_mod.gate_parse(sch, out, project),
        "lib-check": lambda: gate_mod.gate_lib_check(project, sch),
        "erc": lambda: gate_mod.gate_erc(sch, out, project),
        "datasheet": lambda: gate_mod.gate_datasheet(sch, project),
        "spice": lambda: gate_mod.gate_spice(sch, out, project),
    }
    results: dict[str, GateResult] = {}
    for name in selected:
        eprint(f"[verify] гейт {name}...")
        results[name] = runners[name]()
    return results


def finalize_gates(results: dict[str, GateResult], strict: bool) -> None:
    """Пересчитать статусы с учётом --strict и распечатать сводку в stderr."""
    for gate in results.values():
        gate.finalize(strict)
        suffix = f" (артефакт: {gate.artifact})" if gate.artifact else ""
        eprint(f"[verify] {gate.name}: {gate.status}{suffix}")
        for finding in gate.findings:
            eprint(f"    {finding.severity}: {finding.type}: {finding.message}")


def _run(args: argparse.Namespace) -> int:
    """Основной конвейер: резолв путей → гейты → report → exit code.

    Порядок: сначала зависимости, не зависящие от проекта (kicad-cli/пакеты),
    затем резолв проекта/схемы, затем зависимость ngspice (зависит от тестбенча).
    """
    selected = select_gates(args.only)
    check_dependencies(selected)
    project = Path(args.project).resolve()
    if not project.is_dir():
        raise ConfigError(f"проект не найден: {project}")
    sch = resolve_schematic(project, args.sch)
    out = Path(args.out).resolve() if args.out else project / "reports"
    ensure_out_dir(out)
    check_ngspice_dependency(selected, sch)
    results = run_gates(selected, sch, out, project)
    finalize_gates(results, args.strict)
    rep = report.build_report(project, results,
                              report.get_kicad_version(),
                              report.get_revision(project))
    for path in report.write_reports(rep, out, args.format):
        eprint(f"[verify] отчёт: {path}")
    eprint(f"[verify] verdict: {rep.verdict}")
    return EXIT_FAIL if rep.verdict == "fail" else EXIT_PASS


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Точка входа CLI; возвращает exit code (0/1/2/3)."""
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except VerifyError as exc:
        eprint(f"[verify] ошибка: {exc}")
        return exc.code
    except Exception as exc:  # последний рубеж: traceback в stderr, exit 2
        eprint(f"[verify] непредвиденная ошибка: {type(exc).__name__}: {exc}")
        traceback.print_exc(file=sys.stderr)
        return EXIT_CONFIG


if __name__ == "__main__":
    sys.exit(main())
