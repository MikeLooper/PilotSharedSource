"""Pytest configuration that adds a failure report to the end of each test run.

Purpose:
    Lists every failure and error with the line of test code that raised it and
    the actual error. Rule violations also name the specification file and line,
    what was found there, and how to fix it.

Required inputs/arguments:
    None. Pytest loads this file automatically when running OpenAPI/tests.

Required environment/dependencies:
    Python 3.10+ and the packages in OpenAPI/tests/requirements.txt.

Example usage:
    python -m pytest OpenAPI/tests

Expected outputs and failure behavior:
    Prints a "Failures" section before the pytest summary line, or prints nothing
    extra when all tests pass. The report does not change the test results or the
    exit code.
"""

import os
from pathlib import Path

import pytest


def relative(path):
    """Returns a path relative to the current directory when possible."""
    try:
        return os.path.relpath(path)
    except ValueError:
        return str(path)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """Records the actual exception and the test code line that raised it."""
    report = yield
    excinfo = call.excinfo
    if excinfo is not None:
        frames = [
            entry
            for entry in excinfo.traceback
            if Path(entry.path) == Path(item.path)
            and not entry.frame.f_locals.get("__tracebackhide__")
        ]
        if frames:
            report.error_line = frames[-1].lineno + 1
        report.error_text = excinfo.exconly(tryshort=True)
        report.is_rule_violation = excinfo.errisinstance(pytest.fail.Exception)
    return report


def details(report):
    """Returns the lines that explain a failed or errored test."""
    if hasattr(report, "error_text"):
        text = report.error_text.removeprefix("Failed: ")
        lines = text.splitlines()
        if not report.is_rule_violation:
            lines.append("Problem: The test raised this exception before it could finish its checks.")
            lines.append("Fix: Inspect the test code line above and the specification element it reads.")
        return lines
    # Errors while loading the test module, such as invalid YAML, arrive as plain text.
    lines = str(report.longrepr).splitlines()
    return [line[1:].strip() for line in lines if line.startswith("E ")] or lines


def pytest_terminal_summary(terminalreporter, config):
    categories = (("failed", "FAILED"), ("error", "ERROR"))
    entries = [
        (label, report)
        for key, label in categories
        for report in terminalreporter.stats.get(key, [])
    ]
    if not entries:
        return

    terminalreporter.section("Failures")
    for label, report in entries:
        if report.location is None:
            location = relative(config.rootpath)
            line = None
        else:
            path, line, _ = report.location
            line = getattr(report, "error_line", None if line is None else line + 1)
            location = relative(config.rootpath / path)
        if line is not None:
            location = f"{location}:{line}"
        terminalreporter.write_line(f"{label}: {report.nodeid.split('::', 1)[-1]}")
        terminalreporter.write_line(f"  Test code: {location}")
        for text in details(report):
            terminalreporter.write_line(f"  {text}")
