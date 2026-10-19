"""CLI: select_gates/--only и exit-коды реальных прогонов (пункт ревью 8)."""

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import FIXTURES_DIR, REPO_ROOT
from verify.__main__ import GATE_NAMES, select_gates
from verify.schemas import ConfigError


def test_select_gates_no_only_returns_all():
    assert select_gates(None) == list(GATE_NAMES)


def test_select_gates_known_names():
    assert select_gates("spice,parse") == ["parse", "spice"]


def test_select_gates_unknown_name_raises():
    with pytest.raises(ConfigError, match="неизвестные гейты"):
        select_gates("parse,bogus")


def _run_cli(project: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable,
         str(REPO_ROOT / "pipeline" / "verify" / "__main__.py"),
         "--project", str(project), "--only", "parse",
         "--out", str(out)],
        capture_output=True, text=True, cwd=REPO_ROOT, timeout=120)


@pytest.mark.parametrize("fixture", ["simple-divider", "missing-power",
                                     "no-bench"])
def test_cli_only_parse_exit_zero(fixture: str, tmp_path: Path):
    proc = _run_cli(FIXTURES_DIR / fixture, tmp_path / fixture)
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / fixture / "report.json").is_file()
