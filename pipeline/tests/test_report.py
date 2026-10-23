"""markdown-отчёт: экранирование label в позициях (пункт ревью 9)."""

from verify.report import _positions, render_markdown
from verify.schemas import Finding, GateResult, Report


def test_positions_escapes_pipe_and_newline():
    items = [{"description": "a|b\nc", "pos": {"x": 1.0, "y": 2.0}}]
    out = _positions(items)
    assert "|" not in out.replace("\\|", "")
    assert "\n" not in out
    assert "a\\|b c" in out


def test_render_markdown_table_not_broken_by_label():
    gate = GateResult("erc")
    gate.add("error", "erc_violation", "msg",
             [{"description": "pin|name"}])
    report = Report(project="p", gates={"erc": gate},
                    errors=gate.findings)
    md = render_markdown(report)
    error_rows = [line for line in md.splitlines()
                  if "erc_violation" in line]
    # 5 структурных "|" + 1 экранированный внутри ячейки
    assert error_rows and error_rows[0].count("|") == 6
    assert "pin\\|name" in error_rows[0]
