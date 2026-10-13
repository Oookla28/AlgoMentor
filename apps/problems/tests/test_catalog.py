"""Trusted curriculum fixture validation. Production NEVER uses Python exec.

This isolated test harness only evaluates the version-controlled solutions in
CATALOG. It cannot accept student code. It validates authored answers and cases,
not the availability or security of any remote code execution service.
"""
import contextlib
import io
from unittest.mock import patch
import pytest
from apps.problems.services.seed_catalog import CATALOG
from apps.problems.services.judge_service import normalize_output

CASES = [(item, stdin, expected) for item in CATALOG for stdin, expected in item["cases"]]


@pytest.mark.parametrize("item,stdin,expected", CASES, ids=[f"{item['slug']}-{index}" for index, (item, _, _) in enumerate(CASES)])
def test_trusted_reference_solution_matches_authored_case(item, stdin, expected):
    assert any(item is trusted for trusted in CATALOG)
    output = io.StringIO()
    lines = iter(stdin.splitlines())
    with patch("builtins.input", lambda prompt="": next(lines)), contextlib.redirect_stdout(output):
        exec(compile(item["reference_solution"], f"trusted_curriculum:{item['slug']}", "exec"), {"__name__": "__curriculum_test__"})
    assert normalize_output(output.getvalue()) == normalize_output(expected)
