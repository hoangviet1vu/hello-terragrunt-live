"""Property test for ``parse_leaf`` (the Path_Parser).

Covers design Property 3 (parse correctness): for any matched leaf path, the
derived matrix entry satisfies ``entry.tenant == firstSegment(leafPath)`` and
``entry.workDir == parentDirectory(leafPath)`` (the leaf path with
``/terragrunt.hcl`` removed), with ``entry.workDir == tenant + "/" + envDir``.

Validates: Requirements 4.1, 4.2
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

import detect_leaves

# A single path segment of ASCII letters/digits (a valid tenant or env name),
# matching the per-segment alphabet of the anchored leaf pattern.
_segment = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
    min_size=1,
    max_size=8,
)


@st.composite
def _valid_leaf(draw):
    """A well-formed leaf unit path: ``<tenant>/<env>/terragrunt.hcl``.

    Returns ``(leaf_path, tenant, env_dir)`` so the test can assert the parsed
    fields against the segments the path was built from, independently of the
    parser's own splitting logic.
    """
    tenant = draw(_segment)
    env_dir = draw(_segment)
    return f"{tenant}/{env_dir}/terragrunt.hcl", tenant, env_dir


# Feature: terragrunt-pr-merge-workflow, Property 3: parse correctness
#
# For any matched leaf path, the corresponding matrix entry satisfies
# entry.tenant == firstSegment(leafPath) and
# entry.workDir == parentDirectory(leafPath) (the leaf path with
# /terragrunt.hcl removed), with entry.workDir == entry.tenant + "/" + entry.envDir.
#
# Validates: Requirements 4.1, 4.2
@given(leaf=_valid_leaf())
def test_property3_parse_correctness(leaf):
    leaf_path, tenant, env_dir = leaf

    entry = detect_leaves.parse_leaf(leaf_path)

    # Req 4.1: tenant is the first path segment.
    first_segment = leaf_path.split("/")[0]
    assert entry["tenant"] == first_segment
    assert entry["tenant"] == tenant

    # Req 4.2: workDir is the parent directory of the leaf file, i.e. the leaf
    # path with the trailing "/terragrunt.hcl" removed.
    parent_directory = leaf_path.rsplit("/", 1)[0]
    assert entry["workDir"] == parent_directory

    # workDir == tenant + "/" + envDir.
    assert entry["workDir"] == f"{entry['tenant']}/{entry['envDir']}"
    assert entry["workDir"] == f"{tenant}/{env_dir}"

    # The leaf path is carried through unchanged.
    assert entry["leafPath"] == leaf_path
