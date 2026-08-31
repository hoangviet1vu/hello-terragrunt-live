"""Unit tests for the init -> apply gate (``init_apply_gate.sh``).

Exercises the Provision-step gate that runs ``terragrunt init`` and, only on a
zero init exit code, ``terragrunt apply``. The tests drive the real bash script
via ``subprocess`` while replacing the terragrunt binary with a configurable
stub (through the ``TERRAGRUNT_BIN`` testability hook), so no real terragrunt
install is required.

Cases covered:
  * init=1              -> apply is skipped (asserted via an on-disk marker),
                           the gate exits non-zero, and the error names the
                           WORKDIR and the failed "init" step.
  * init=0 / apply=0    -> the gate exits zero.
  * init=0 / apply=1    -> the gate exits non-zero, and the error names the
                           WORKDIR and the failed "apply" step.

WORKDIR is a ``<tenant>/<env>`` path (e.g. "PRDCV/dev"); the tests assert that
path appears verbatim in the emitted error annotations.

Requirements: 10.2, 10.3, 10.5, 10.6, 11.1, 11.2
"""

from __future__ import annotations

import os
import subprocess

import pytest

# Absolute path to the script under test (sibling of the ``tests`` directory).
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GATE_SCRIPT = os.path.join(_SCRIPTS_DIR, "init_apply_gate.sh")

# A representative <tenant>/<env> leaf path used across the cases.
_WORKDIR = "PRDCV/dev"


def _write_stub(tmp_path, *, init_rc: int, apply_rc: int, apply_marker):
    """Create a stub terragrunt script and return its path.

    The stub distinguishes ``init`` from ``apply`` by its first argument. On
    ``apply`` it first touches ``apply_marker`` so tests can prove whether apply
    ran, then exits with the configured code. Any other subcommand exits 0.
    """
    stub = tmp_path / "terragrunt_stub.sh"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'sub="$1"\n'
        'if [ "$sub" = "init" ]; then\n'
        f"  exit {init_rc}\n"
        'elif [ "$sub" = "apply" ]; then\n'
        f'  touch "{apply_marker}"\n'
        f"  exit {apply_rc}\n"
        "fi\n"
        "exit 0\n"
    )
    stub.chmod(0o755)
    return stub


def _run_gate(stub_path, *, workdir: str = _WORKDIR):
    """Invoke the gate script with the stubbed terragrunt binary."""
    env = dict(os.environ)
    env["WORKDIR"] = workdir
    env["TERRAGRUNT_BIN"] = str(stub_path)
    return subprocess.run(
        ["bash", _GATE_SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )


def test_init_failure_skips_apply_and_fails(tmp_path):
    """init=1 must skip apply, exit non-zero, and name WORKDIR + init."""
    apply_marker = tmp_path / "apply_ran.marker"
    stub = _write_stub(tmp_path, init_rc=1, apply_rc=0, apply_marker=apply_marker)

    result = _run_gate(stub)

    assert result.returncode != 0, result.stderr
    # apply must NOT have run after a failed init.
    assert not apply_marker.exists(), "apply ran despite init failure"
    assert _WORKDIR in result.stderr
    assert "init" in result.stderr


def test_init_and_apply_success(tmp_path):
    """init=0 / apply=0 succeeds with a zero exit code."""
    apply_marker = tmp_path / "apply_ran.marker"
    stub = _write_stub(tmp_path, init_rc=0, apply_rc=0, apply_marker=apply_marker)

    result = _run_gate(stub)

    assert result.returncode == 0, result.stderr
    # apply is reached only on a zero init exit code.
    assert apply_marker.exists(), "apply did not run after successful init"


def test_apply_failure_fails(tmp_path):
    """init=0 / apply=1 exits non-zero and names WORKDIR + apply."""
    apply_marker = tmp_path / "apply_ran.marker"
    stub = _write_stub(tmp_path, init_rc=0, apply_rc=1, apply_marker=apply_marker)

    result = _run_gate(stub)

    assert result.returncode != 0, result.stderr
    assert apply_marker.exists(), "apply did not run after successful init"
    assert _WORKDIR in result.stderr
    assert "apply" in result.stderr


@pytest.mark.parametrize("workdir", ["PRDCV/dev", "SAMPLETENANT/prod"])
def test_error_reports_tenant_env_path(tmp_path, workdir):
    """Error annotations report the failing <tenant>/<env> path verbatim."""
    apply_marker = tmp_path / "apply_ran.marker"
    stub = _write_stub(tmp_path, init_rc=1, apply_rc=0, apply_marker=apply_marker)

    result = _run_gate(stub, workdir=workdir)

    assert result.returncode != 0
    assert workdir in result.stderr
