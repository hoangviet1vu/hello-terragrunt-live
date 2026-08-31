"""Unit tests for ``validate_entry.sh`` (Validate matrix entry step).

The helper validates a single provision matrix entry before provisioning:
it fails with an identifying ``::error::`` message when any of the tenant,
workDir, or leafPath fields is empty (Requirement 5.6), and fails with a
``::error::leafPath is malformed: ...`` message when the leaf path is not of
the form ``<seg>/<seg>/.../<file>`` (Requirement 4.4).

These tests shell out to the script with pytest + subprocess. Each of the
three required fields is blanked in turn, asserting that the emitted error
names the missing field and that the exit code is non-zero. A well-formed
entry (exit 0) and a malformed leafPath are also covered.

Validates: Requirements 5.6
"""

from __future__ import annotations

import os
import subprocess

import pytest

# Absolute path to the script under test (sibling of the tests directory's parent).
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VALIDATE_ENTRY = os.path.join(_SCRIPTS_DIR, "validate_entry.sh")

# A well-formed baseline entry: <tenant>/<env>/<file> leaf path with a tenant
# identifier and working directory.
_VALID_TENANT = "PRDCV"
_VALID_WORKDIR = "PRDCV/dev"
_VALID_LEAFPATH = "PRDCV/dev/terragrunt.hcl"


def _run(tenant, workdir, leafpath):
    """Invoke validate_entry.sh with the given fields via environment variables.

    Returns the completed process (with captured stdout/stderr as text).
    """
    env = os.environ.copy()
    env["TENANT"] = tenant
    env["WORKDIR"] = workdir
    env["LEAFPATH"] = leafpath
    return subprocess.run(
        ["bash", _VALIDATE_ENTRY],
        env=env,
        capture_output=True,
        text=True,
    )


# --- Valid entry ------------------------------------------------------------


def test_valid_entry_exits_zero():
    """A well-formed entry succeeds with exit 0 and no error output."""
    result = _run(_VALID_TENANT, _VALID_WORKDIR, _VALID_LEAFPATH)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "::error::" not in (result.stdout + result.stderr)


# --- Missing field checks (Requirement 5.6) ---------------------------------


@pytest.mark.parametrize(
    "tenant,workdir,leafpath,field",
    [
        ("", _VALID_WORKDIR, _VALID_LEAFPATH, "tenant"),
        (_VALID_TENANT, "", _VALID_LEAFPATH, "workDir"),
        (_VALID_TENANT, _VALID_WORKDIR, "", "leafPath"),
    ],
)
def test_blank_field_fails_and_names_missing_field(tenant, workdir, leafpath, field):
    """Blanking each field in turn fails with an error naming that field."""
    result = _run(tenant, workdir, leafpath)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert f"::error::missing {field}" in output, output


# --- Malformed leaf path (Requirement 4.4) ----------------------------------


@pytest.mark.parametrize(
    "leafpath",
    [
        "terragrunt.hcl",  # single segment, no leading directories
        "dev/terragrunt.hcl",  # only one leading directory segment
        "/PRDCV/dev/terragrunt.hcl",  # leading slash
        "PRDCV/dev/",  # trailing slash
        "PRDCV//terragrunt.hcl",  # empty middle segment
    ],
)
def test_malformed_leafpath_fails(leafpath):
    """A malformed leaf path fails with a malformed-path error naming the path."""
    result = _run(_VALID_TENANT, _VALID_WORKDIR, leafpath)
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert f"::error::leafPath is malformed: {leafpath}" in output, output
