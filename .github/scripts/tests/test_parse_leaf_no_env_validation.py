"""Example tests: ``parse_leaf`` performs no environment-name validation.

Requirement 4.3 states the Path_Parser SHALL NOT derive or validate any
environment name from the leaf path -- ``envDir`` is carried verbatim for
reporting only. These example/unit tests confirm ``parse_leaf`` accepts
arbitrary ``envDir`` values without rejecting them or normalizing them: the
second path segment is echoed back unchanged regardless of what it contains.

Note: ``parse_leaf`` only guards against a malformed path having fewer than two
directory segments before the file name (Req 4.4). That guard is about path
*shape*, not environment-name *content*, so any non-empty second segment -- no
matter how unconventional -- must be accepted verbatim.

Validates: Requirements 4.3
"""

from __future__ import annotations

import pytest

import detect_leaves

# A deliberately wide set of second-segment ("envDir") values. None of these is
# a "known" environment name (dev/prod/etc.); the parser must accept every one
# without rejecting, normalizing, lowercasing, or otherwise validating it.
_ARBITRARY_ENV_DIRS = [
    "dev",
    "prod",
    "DEV",  # uppercase -- not lowercased
    "Staging",  # mixed case -- preserved
    "PRODUCTION",
    "qa1",
    "123",  # purely numeric
    "0",
    "env-with-dashes",  # dashes are not letters/digits, still carried verbatim
    "env_with_underscores",
    "env.with.dots",
    "totally-made-up-name",
    "x",  # single char
    "environment name with spaces",
    "UPPER-lower-123",
    "\u00e9\u00e8\u00ea",  # non-ASCII characters
    "\u4e2d\u6587",  # CJK characters
]


@pytest.mark.parametrize("env_dir", _ARBITRARY_ENV_DIRS)
def test_parse_leaf_carries_arbitrary_env_dir_verbatim(env_dir):
    """The second path segment is returned as ``envDir`` unchanged."""
    tenant = "TENANT"
    path = f"{tenant}/{env_dir}/terragrunt.hcl"

    result = detect_leaves.parse_leaf(path)

    # envDir is carried verbatim -- no validation, no normalization.
    assert result["envDir"] == env_dir
    # workDir is simply "<tenant>/<envDir>" regardless of envDir content.
    assert result["workDir"] == f"{tenant}/{env_dir}"
    # tenant and leafPath remain the first segment and the input path.
    assert result["tenant"] == tenant
    assert result["leafPath"] == path


@pytest.mark.parametrize("env_dir", _ARBITRARY_ENV_DIRS)
def test_parse_leaf_does_not_reject_arbitrary_env_dir(env_dir):
    """No exception is raised for any arbitrary (non-empty) env segment."""
    path = f"TENANT/{env_dir}/terragrunt.hcl"

    # Must not raise -- there is no env-validation branch to reject these.
    detect_leaves.parse_leaf(path)


def test_parse_leaf_accepts_env_dir_regardless_of_filename():
    """envDir handling is independent of the trailing file name.

    ``parse_leaf`` operates on path shape, not on the environment name's
    meaning, so it accepts an unusual envDir even when the final segment is not
    ``terragrunt.hcl`` -- confirming there is no env-specific validation branch.
    """
    path = "TENANT/some-unusual-env/main.tf"

    result = detect_leaves.parse_leaf(path)

    assert result["envDir"] == "some-unusual-env"
    assert result["tenant"] == "TENANT"
    assert result["workDir"] == "TENANT/some-unusual-env"
    assert result["leafPath"] == path


def test_parse_leaf_only_guards_path_shape_not_env_content():
    """The single guard is about path shape (Req 4.4), not env-name content.

    A path with fewer than two directory segments before the file name is
    malformed and rejected -- but this is a *shape* check, not an
    *environment-name* check. Confirm the rejection is unrelated to envDir
    content by showing a two-segment path (no envDir at all) is what triggers
    it.
    """
    with pytest.raises(detect_leaves.MalformedLeafPathError):
        detect_leaves.parse_leaf("TENANT/terragrunt.hcl")
