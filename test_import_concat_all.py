#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "pytest",
# ]
# ///

"""Tests for import_concat_all.sh's failure report.

Run with `./test_import_concat_all.py`. The real importer is swapped for a
stub through IMPORT_CONCAT, so nothing is fetched. The script needs bash 4 or
later (it uses associative arrays), so on macOS's bash 3.2 the tests skip; CI
runs them on Linux.
"""

import os
import pathlib
import re
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).parent
SCRIPT = HERE / "import_concat_all.sh"

# Fails the sources named in STUB_FAIL, printing STUB_ERROR as its last line.
STUB = """#!/usr/bin/env bash
echo "importing $1" >&2
case ",$STUB_FAIL," in
    *",$1,"*)
        echo "Traceback (most recent call last):" >&2
        printf '%s\\n\\n' "$STUB_ERROR" >&2
        exit 1 ;;
esac
"""


def bash_major():
    out = subprocess.run(
        ["bash", "-c", "echo ${BASH_VERSINFO[0]}"], capture_output=True, text=True
    )
    return int(out.stdout.strip() or 0)


pytestmark = pytest.mark.skipif(bash_major() < 4, reason="needs bash 4 or later")


@pytest.fixture
def run_all(tmp_path):
    stub = tmp_path / "stub_import.sh"
    stub.write_text(STUB)
    stub.chmod(0o755)

    def run(
        fail=(),
        error="httpx.HTTPStatusError: Client error '403 Forbidden'",
        failures_file=True,
        report=None,
    ):
        env = {
            **os.environ,
            "IMPORT_CONCAT": str(stub),
            "STUB_FAIL": ",".join(fail),
            "STUB_ERROR": error,
        }
        report = report or tmp_path / "failures.txt"
        if failures_file:
            env["CONCAT_FAILURES_FILE"] = str(report)
        else:
            env.pop("CONCAT_FAILURES_FILE", None)
        result = subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, cwd=tmp_path
        )
        return result, report

    return run


def test_each_failed_source_is_reported_with_its_error(run_all):
    result, report = run_all(fail=["palmetto-fur-the-season.json", "furski.json"])

    assert result.returncode == 0
    lines = sorted(report.read_text().splitlines())
    assert lines == [
        "furski.json https://reg.fur.ski: httpx.HTTPStatusError: Client error '403 Forbidden'",
        "palmetto-fur-the-season.json https://reg.palmettofurtheseason.org: "
        "httpx.HTTPStatusError: Client error '403 Forbidden'",
    ]


def test_the_report_is_empty_when_every_source_imports(run_all):
    """A leftover file from an earlier run must not fail this one."""
    _, report = run_all(fail=["furski.json"])
    assert report.read_text()

    result, report = run_all()

    assert result.returncode == 0
    assert report.read_text() == ""


def test_upstream_error_text_stays_on_one_bounded_line(run_all):
    """The error can quote the upstream site, and the workflow echoes it."""
    _, report = run_all(fail=["furski.json"], error="KeyError: 'x\r" + "y" * 5000)

    (line,) = report.read_text().splitlines()
    assert "\r" not in line
    assert len(line) < 400


def test_every_source_still_logs_its_output(run_all):
    result, _ = run_all(fail=["furski.json"])

    assert len(re.findall(r"^importing ", result.stderr, re.M)) == len(
        re.findall(r"^run ", SCRIPT.read_text(), re.M)
    )
    assert "Traceback" in result.stderr
    assert "::error::  - furski.json https://reg.fur.ski: " in result.stdout


def test_without_a_report_file_it_behaves_as_before(run_all):
    result, report = run_all(fail=["furski.json"], failures_file=False)

    assert result.returncode == 0
    assert not report.exists()
    assert "::error::import_concat: 1 source(s) failed" in result.stdout


def test_an_unwritable_report_fails_the_script(run_all, tmp_path):
    """Exiting 0 here would leave the caller an empty report, which reads as success."""
    result, _ = run_all(fail=["furski.json"], report=tmp_path / "missing" / "failures.txt")

    assert result.returncode != 0
    assert "can't write CONCAT_FAILURES_FILE" in result.stdout


def test_a_report_that_becomes_unwritable_fails_the_script(run_all, tmp_path):
    """The final write is checked too, not only the one before importing."""
    report = tmp_path / "failures.txt"
    stub = tmp_path / "stub_import.sh"
    stub.write_text(STUB.replace("exit 1 ;;", f'chmod 0444 "{report}"; exit 1 ;;'))

    result, _ = run_all(fail=["furski.json"], report=report)

    assert result.returncode != 0
    assert "can't write CONCAT_FAILURES_FILE" in result.stdout


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", *sys.argv[1:]]))
