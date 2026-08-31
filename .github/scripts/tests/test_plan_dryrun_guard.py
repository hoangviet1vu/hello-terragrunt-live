"""Guard tests for the terragrunt plan dry-run harness (Task 13.1).

The terragrunt ``plan`` dry-run (``terragrunt_plan_dryrun.sh``) confirms
backend resolution, module auth, and working-directory selection against a
fixture leaf *without applying* (Req 9.2, 9.3, 10.1). It needs live
credentials, network access, and the ``terragrunt`` binary, so the full plan
path is optional / manual.

These tests exercise the harness's **gating** behavior offline so the script is
proven runnable and safe to wire into a pipeline:

- When prerequisites (terragrunt binary / credentials / secrets) are missing,
  it SKIPs (exit 0) and makes no terragrunt call.
- With ``TG_DRYRUN_STRICT=1`` the same missing prerequisites become a hard
  failure (exit 1), so a pipeline can opt into strict enforcement.
- An invalid scheme argument is a usage error (exit 1).

The actual ``terragrunt init``/``plan`` invocation is not run here; it belongs
to the manual/optional path documented in ``fixtures/README.md``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "terragrunt_plan_dryrun.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash is required to run the dry-run harness"
)

# Env that would otherwise let the harness proceed; cleared per-test so the
# guard logic is what we observe, not the developer's real credentials.
_LIVE_ENV_VARS = (
    "TG_STATE_BUCKET",
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "TOKEN",
    "SECURITY_KEY",
)


def _clean_env(**overrides: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _LIVE_ENV_VARS}
    # Force the "terragrunt missing" gate to be deterministic regardless of the
    # host by pointing at a non-existent binary unless a test overrides it.
    env.setdefault("TG_DRYRUN_TERRAGRUNT", "terragrunt-does-not-exist-xyz")
    env.update(overrides)
    return env


def _run(scheme: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = ["bash", str(SCRIPT)]
    if scheme is not None:
        cmd.append(scheme)
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def test_skips_cleanly_when_terragrunt_missing():
    """Missing terragrunt binary -> SKIP (exit 0), no plan attempted."""
    result = _run("https", env=_clean_env())
    assert result.returncode == 0, result.stderr
    assert "SKIP" in result.stdout


def test_skips_cleanly_when_credentials_missing():
    """terragrunt present but creds missing -> SKIP (exit 0)."""
    # Pretend terragrunt exists by pointing at any real executable; the harness
    # only checks presence on PATH via command -v, and the credential gate
    # fires before any invocation.
    env = _clean_env(TG_DRYRUN_TERRAGRUNT="bash")
    result = _run("https", env=env)
    assert result.returncode == 0, result.stderr
    assert "SKIP" in result.stdout
    # Credential gate should mention a required backend variable.
    assert "TG_STATE_BUCKET" in result.stdout or "AWS_REGION" in result.stdout


def test_strict_mode_fails_on_missing_prerequisites():
    """TG_DRYRUN_STRICT=1 turns a missing prerequisite into a hard failure."""
    env = _clean_env(TG_DRYRUN_STRICT="1")
    result = _run("https", env=env)
    assert result.returncode == 1
    assert "::error::" in result.stderr


def test_invalid_scheme_is_usage_error():
    """An unknown scheme argument is a usage error (exit 1)."""
    result = _run("bogus", env=_clean_env())
    assert result.returncode == 1
    assert "usage" in result.stderr.lower()


def test_ssh_scheme_gates_on_security_key():
    """The ssh scheme skips when SECURITY_KEY is absent (given other creds set)."""
    env = _clean_env(
        TG_DRYRUN_TERRAGRUNT="bash",
        TG_STATE_BUCKET="fixture-bucket",
        AWS_REGION="ap-southeast-2",
        AWS_ACCESS_KEY_ID="AKIA_FIXTURE",
        AWS_SECRET_ACCESS_KEY="secret_fixture",
    )
    result = _run("ssh", env=env)
    assert result.returncode == 0, result.stderr
    assert "SKIP" in result.stdout
    assert "SECURITY_KEY" in result.stdout
