"""Property test for the count-and-empty behavior of ``build_matrix``.

Covers design Property 5: for any list of changed file paths that yields N
matched leaf units with 0 <= N <= 256, the emitted matrix has exactly N
entries; and when N == 0 the emitted matrix is the empty array (so no
Provision_Job is produced).

Validates: Requirements 2.4, 3.4, 5.1, 5.2, 5.4
"""

from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

import detect_leaves

# The authoritative leaf regex, defined independently of the implementation so
# the property checks behavior against the specification rather than the code.
_LEAF_REGEX = re.compile(r"^[A-Za-z0-9]+/[A-Za-z0-9]+/terragrunt\.hcl$")

# A single path segment of ASCII letters/digits (a valid tenant or env name).
_segment = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
    min_size=1,
    max_size=6,
)

# Valid leaf units: <tenant>/<env>/terragrunt.hcl.
_valid_leaf = st.builds(
    lambda tenant, env: f"{tenant}/{env}/terragrunt.hcl",
    _segment,
    _segment,
)

# Non-matching paths: near-miss roots, deep paths, and arbitrary junk. None of
# these satisfy the leaf regex, so they never contribute to the matched count.
_non_matching = st.one_of(
    st.just("root.hcl"),
    _segment.map(lambda s: f"{s}/root.hcl"),
    st.builds(lambda a, b: f"{a}/{b}/root.hcl", _segment, _segment),
    st.just("terragrunt.hcl"),
    st.builds(lambda a, b, c: f"{a}/{b}/{c}/terragrunt.hcl", _segment, _segment, _segment),
    st.builds(lambda a, b: f"{a}/{b}/main.tf", _segment, _segment),
    st.text(max_size=20),
)

# A mixed list of valid leaves and non-matching paths. Bounded at 256 total so
# the matched count stays within the cap (0 <= N <= 256), keeping this property
# focused on the in-range count behavior (Property 6 covers the >256 boundary).
_mixed_paths = st.lists(
    st.one_of(_valid_leaf, _non_matching),
    max_size=256,
)


# Feature: terragrunt-pr-merge-workflow, Property 5: count and empty behavior
# For any list of changed file paths that yields N matched leaf units with
# 0 <= N <= 256, the emitted matrix has exactly N entries; and when N == 0 the
# emitted matrix is the empty array (so no Provision_Job is produced).
# Validates: Requirements 2.4, 3.4, 5.1, 5.2, 5.4
@given(paths=_mixed_paths)
def test_property_matrix_count_and_empty(paths):
    # Expected N: distinct regex-matching paths (build_matrix de-duplicates).
    expected_n = len({p for p in paths if _LEAF_REGEX.match(p)})
    assert 0 <= expected_n <= detect_leaves.MAX_MATRIX_SIZE

    entries, has_units = detect_leaves.build_matrix(paths)

    # matrix length == N for the full 0..256 range (Req 5.1, 5.2).
    assert len(entries) == expected_n

    if expected_n == 0:
        # N == 0 yields the empty array and no provision job (Req 2.4, 3.4, 5.4).
        assert entries == []
        assert has_units is False
    else:
        # Any positive count produces units to fan out over.
        assert has_units is True
