"""Unit tests for the merged-state guard (``guard_merged_state.sh``).

The guard confirms that a pull request's merged state is a determinable
boolean before change detection runs. It exits 0 for exactly ``"true"`` or
``"false"`` and exits 1 with ``::error::merged state indeterminable`` on stderr
for anything else -- empty, ``"null"``, ``"yes"``, etc. (Requirement 1.5).

These tests invoke the script as a subprocess and assert on its exit code and
stderr, passing the merged value both as the positional argument and via the
``MERGED`` environment variable.
"""

from __future__ import annotations

import os
import subprocess

import pytest

# Absolute path to the guard script under test (.github/scripts/guard_merged_state.sh).
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GUARD = os.path.join(_SCRIPTS_DIR, "guard_merged_state.sh")

_INDETERMINABLE_ERROR = "::error::merged state indeterminable"


def _run_with_arg(value):
    """Invoke the guard passing ``value`` as the positional argument ($1)."""
    return subprocess.run(
        ["bash", _GUARD, value],
        capture_output=True,
        text=True,
    )


def _run_with_env(value):
    """Invoke the guard passing ``value`` via the MERGED environment variable."""
    env = dict(os.environ, MERGED=value)
    return subprocess.run(
        ["bash", _GUARD],
        capture_output=True,
        text=True,
        env=env,
    )


# --- Determinable states: exit 0, no error -----------------------------------


@pytest.mark.parametrize("value", ["true", "false"])
def test_determinable_arg_exits_zero(value):
    """"true"/"false" as $1 -> exit 0 and no indeterminable error."""
    result = _run_with_arg(value)
    assert result.returncode == 0
    assert _INDETERMINABLE_ERROR not in result.stderr


@pytest.mark.parametrize("value", ["true", "false"])
def test_determinable_env_exits_zero(value):
    """"true"/"false" via MERGED env -> exit 0 and no indeterminable error."""
    result = _run_with_env(value)
    assert result.returncode == 0
    assert _INDETERMINABLE_ERROR not in result.stderr


# --- Indeterminable states: exit 1, error on stderr (Req 1.5) ----------------


@pytest.mark.parametrize("value", ["", "null", "yes"])
def test_indeterminable_arg_exits_one_with_error(value):
    """"", "null", "yes" as $1 -> exit 1 with the indeterminable error."""
    result = _run_with_arg(value)
    assert result.returncode == 1
    assert _INDETERMINABLE_ERROR in result.stderr


@pytest.mark.parametrize("value", ["", "null", "yes"])
def test_indeterminable_env_exits_one_with_error(value):
    """"", "null", "yes" via MERGED env -> exit 1 with the indeterminable error."""
    result = _run_with_env(value)
    assert result.returncode == 1
    assert _INDETERMINABLE_ERROR in result.stderr


def test_missing_value_is_indeterminable():
    """No argument and no MERGED env var -> empty string -> exit 1 with error."""
    env = {k: v for k, v in os.environ.items() if k != "MERGED"}
    result = subprocess.run(
        ["bash", _GUARD],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert _INDETERMINABLE_ERROR in result.stderr
