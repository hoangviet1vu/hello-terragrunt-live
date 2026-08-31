"""Property test for the exclusion invariant of ``filter_leaves``.

Covers design Property 2: the emitted matrix (equivalently, the kept path set)
never includes a ``root.hcl`` at any depth, a repo-root ``terragrunt.hcl``
(single path segment with no parent directory), or any path with fewer than two
directory segments before the file name (Requirements 2.2, 2.3, 4.4).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

import detect_leaves

# --- Generators -------------------------------------------------------------
# A single path segment of ASCII letters/digits (matches the leaf pattern's
# per-segment alphabet).
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

# root.hcl placed at a variety of depths (including the repo root).
_root_hcl = st.lists(_segment, min_size=0, max_size=4).map(
    lambda parts: "/".join([*parts, "root.hcl"])
)

# terragrunt.hcl placed at a variety of depths, including the excluded
# single-segment (repo-root) case and over-deep cases.
_terragrunt_hcl_various_depths = st.lists(_segment, min_size=0, max_size=4).map(
    lambda parts: "/".join([*parts, "terragrunt.hcl"])
)

# Malformed / near-miss arbitrary paths.
_arbitrary_path = st.text(max_size=40)

# A mixed list of paths spanning valid leaves and every kind of excludable path.
_path_list = st.lists(
    st.one_of(
        _valid_leaf,
        _root_hcl,
        _terragrunt_hcl_various_depths,
        _arbitrary_path,
    ),
    max_size=30,
)


# --- Property-based test ----------------------------------------------------
# Feature: terragrunt-pr-merge-workflow, Property 2: For any list of changed
# file paths, no entry in the emitted matrix has a leaf path whose basename is
# root.hcl, whose value is a repo-root terragrunt.hcl (a single path segment
# with no parent directory), or which has fewer than two directory segments
# before the file name.
# Validates: Requirements 2.2, 2.3, 4.4


@given(paths=_path_list)
def test_property_exclusion_invariant(paths):
    kept = detect_leaves.filter_leaves(paths)
    for path in kept:
        # 2.2: no kept path has basename root.hcl (at any depth).
        assert path.rsplit("/", 1)[-1] != "root.hcl"

        segments = path.split("/")

        # 2.3: no kept path is a single-segment (repo-root) terragrunt.hcl.
        assert not (len(segments) == 1 and segments[0] == "terragrunt.hcl")

        # 4.4: no kept path has fewer than two directory segments before the
        # file name (a leaf needs <tenant>/<env>/ before terragrunt.hcl).
        assert len(segments) - 1 >= 2
