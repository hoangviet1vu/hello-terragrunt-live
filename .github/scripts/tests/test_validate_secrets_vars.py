"""Unit tests for the ``validate_secrets_vars.sh`` provision-step helper.

The helper confirms the always-required GitHub Environment variables
(``TG_STATE_BUCKET``, ``AWS_REGION``) and secrets (``AWS_ACCESS_KEY_ID``,
``AWS_SECRET_ACCESS_KEY``) are present and non-empty *before* any Terragrunt
invocation or remote-state access. If any value is missing or empty it exits
non-zero and emits a ``::error::`` annotation naming the first missing value.

These tests drive the script as a subprocess with a controlled environment:

- Blank each required var/secret in turn and assert a non-zero exit whose
  ``::error::`` message names that value (Req 6.4, 7.3, 7.4, 8.4, 8.5).
- All values present -> exit 0 (the pass case).
- The script performs no Terragrunt call, so the "before any Terragrunt call"
  guarantee is structural: it only validates and returns. To prove nothing
  reaches Terragrunt (and therefore no remote-state access happens, Req 7.5),
  each run is given a PATH-shimmed ``terragrunt`` that writes a marker file when
  invoked; every test asserts the marker is absent afterwards.

Validates: Requirements 6.4, 7.3, 7.4, 7.5, 8.4, 8.5
"""

from __future__ import annotations

import os
import subprocess

import pytest

# Absolute path to the script under test (sibling of the ``tests`` directory).
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_SCRIPTS_DIR, "validate_secrets_vars.sh")

# The always-required values, in the order the script reports them.
REQUIRED_VALUES = [
    "TG_STATE_BUCKET",
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
]

# Non-empty placeholder values used to populate a fully-present environment.
# Values are arbitrary and non-sensitive; the script never inspects contents.
_PRESENT_ENV = {
    "TG_STATE_BUCKET": "example-state-bucket",
    "AWS_REGION": "ap-southeast-2",
    "AWS_ACCESS_KEY_ID": "AKIAEXAMPLE",
    "AWS_SECRET_ACCESS_KEY": "examplesecret",
}


def _make_terragrunt_shim(tmp_path):
    """Create a PATH directory holding a ``terragrunt`` shim.

    The shim writes a marker file if it is ever executed, so tests can prove the
    validation helper never invokes Terragrunt. Returns ``(shim_dir, marker)``.
    """
    shim_dir = tmp_path / "shim-bin"
    shim_dir.mkdir()
    marker = tmp_path / "terragrunt-was-called"
    shim = shim_dir / "terragrunt"
    shim.write_text(
        "#!/usr/bin/env bash\n"
        f'echo "invoked" > "{marker}"\n'
        "exit 0\n"
    )
    shim.chmod(0o755)
    return shim_dir, marker


def _run(env_overrides, tmp_path):
    """Run the script with a controlled environment and a terragrunt shim.

    ``env_overrides`` maps required-value names to the value to set. A value of
    ``None`` unsets the variable; an empty string sets it to empty. Returns
    ``(completed_process, marker_path)``.
    """
    shim_dir, marker = _make_terragrunt_shim(tmp_path)

    # Start from a minimal, deterministic environment. Put the shim dir first on
    # PATH so any ``terragrunt`` invocation resolves to the marker-writing shim.
    env = {"PATH": f"{shim_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    for name in REQUIRED_VALUES:
        value = env_overrides.get(name, _PRESENT_ENV[name])
        if value is not None:
            env[name] = value

    proc = subprocess.run(
        ["bash", _SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )
    return proc, marker


def test_all_present_exits_zero_and_no_terragrunt_call(tmp_path):
    # Every required value present and non-empty -> success, and Terragrunt is
    # never invoked. (pass case; Req 7.5 structural guarantee)
    proc, marker = _run({}, tmp_path)

    assert proc.returncode == 0, proc.stderr
    assert not marker.exists(), "terragrunt must not be invoked by validation"


@pytest.mark.parametrize("blanked", REQUIRED_VALUES)
def test_empty_value_fails_naming_it_before_terragrunt(blanked, tmp_path):
    # Blank each required var/secret in turn (set to empty string): the script
    # must exit non-zero, name the blanked value in a ::error:: annotation, and
    # never reach a Terragrunt call. (Req 6.4, 7.3, 7.4, 8.4, 8.5, 7.5)
    proc, marker = _run({blanked: ""}, tmp_path)

    assert proc.returncode != 0
    assert "::error::" in proc.stderr
    assert blanked in proc.stderr
    assert not marker.exists(), "terragrunt must not be invoked when a value is missing"


@pytest.mark.parametrize("unset", REQUIRED_VALUES)
def test_unset_value_fails_naming_it_before_terragrunt(unset, tmp_path):
    # Same as above but the value is entirely unset (not just empty), exercising
    # the ``set -u``-safe indirect expansion path. (Req 6.4, 7.3, 7.4, 8.4, 8.5)
    proc, marker = _run({unset: None}, tmp_path)

    assert proc.returncode != 0
    assert "::error::" in proc.stderr
    assert unset in proc.stderr
    assert not marker.exists(), "terragrunt must not be invoked when a value is missing"


def test_first_missing_value_is_reported_in_declared_order(tmp_path):
    # When several values are missing, the earliest in the declared order
    # (variables before secrets) is the one named, so backend-config problems
    # surface first. (ordering aspect of Req 7.3/7.4 vs 8.4/8.5)
    proc, marker = _run(
        {"TG_STATE_BUCKET": "", "AWS_SECRET_ACCESS_KEY": ""}, tmp_path
    )

    assert proc.returncode != 0
    assert "TG_STATE_BUCKET" in proc.stderr
    # The later-ordered secret must not be the one reported first.
    assert "AWS_SECRET_ACCESS_KEY" not in proc.stderr
    assert not marker.exists()
