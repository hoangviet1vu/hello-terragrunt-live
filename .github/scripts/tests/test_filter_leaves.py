"""Property test for ``filter_leaves`` (the anchored leaf-unit path filter).

Covers the master filter-correctness property (design Property 1): for any list
of changed file paths, the set of paths kept equals exactly the subset matching
the anchored leaf regex ``^[A-Za-z0-9]+/[A-Za-z0-9]+/terragrunt\\.hcl$`` -- no
false positives and no false negatives.

Validates: Requirements 2.1, 3.2
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


@st.composite
def _valid_leaf(draw):
    """A well-formed leaf unit path: ``<tenant>/<env>/terragrunt.hcl``."""
    return f"{draw(_segment)}/{draw(_segment)}/terragrunt.hcl"


@st.composite
def _near_miss_root(draw):
    """A root-config-ish path that must never match the leaf regex.

    Covers ``root.hcl`` at various depths and a top-level ``terragrunt.hcl``.
    """
    kind = draw(st.integers(min_value=0, max_value=4))
    if kind == 0:
        return "root.hcl"  # repo-root root.hcl
    if kind == 1:
        return f"{draw(_segment)}/root.hcl"  # root.hcl one level down
    if kind == 2:
        return f"{draw(_segment)}/{draw(_segment)}/root.hcl"  # leaf-depth root.hcl
    if kind == 3:
        return "terragrunt.hcl"  # repo-root terragrunt.hcl
    return f"{draw(_segment)}/root.hcl"


@st.composite
def _deep_path(draw):
    """A too-deep path (4+ segments) that must never match."""
    depth = draw(st.integers(min_value=3, max_value=6))
    segments = [draw(_segment) for _ in range(depth)]
    return "/".join(segments) + "/terragrunt.hcl"


@st.composite
def _malformed_path(draw):
    """An arbitrary / malformed path that usually does not match the regex."""
    return draw(
        st.one_of(
            st.just(""),
            _segment,  # single segment, no directories
            st.text(max_size=30),  # arbitrary junk (may contain "/" etc.)
            # Correct depth but wrong filename.
            st.builds(lambda a, b: f"{a}/{b}/main.tf", _segment, _segment),
            # Correct shape but a segment with a disallowed character.
            st.builds(lambda a: f"{a}/de-v/terragrunt.hcl", _segment),
            st.builds(lambda a: f"ten_ant/{a}/terragrunt.hcl", _segment),
        )
    )


# A mixed path list drawing from every category above, so each generated input
# exercises valid leaves alongside near-miss roots, deep paths, and malformed
# entries in arbitrary interleavings.
_mixed_paths = st.lists(
    st.one_of(
        _valid_leaf(),
        _near_miss_root(),
        _deep_path(),
        _malformed_path(),
    ),
    max_size=40,
)


# Feature: terragrunt-pr-merge-workflow, Property 1: filter correctness
# For any list of changed file paths, the set of paths filter_leaves keeps
# equals exactly the subset of those paths matching
# ^[A-Za-z0-9]+/[A-Za-z0-9]+/terragrunt\.hcl$ -- no path outside that set is
# kept (no false positives) and every path inside it is kept (no false
# negatives). Ordering is preserved and duplicates are removed (first wins).
# Validates: Requirements 2.1, 3.2
@given(paths=_mixed_paths)
def test_property_filter_matches_leaf_regex_exactly(paths):
    result = detect_leaves.filter_leaves(paths)

    # Expected: the regex-satisfying subset, first occurrence kept, order preserved.
    expected: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        if _LEAF_REGEX.match(path):
            expected.append(path)
            seen.add(path)

    # No false positives / no false negatives, with dedup and order preserved.
    assert result == expected

    # Every kept path genuinely matches the leaf regex (no false positives).
    for path in result:
        assert _LEAF_REGEX.match(path), path

    # Every regex-matching input appears in the output (no false negatives).
    matching_inputs = {p for p in paths if _LEAF_REGEX.match(p)}
    assert matching_inputs == set(result)

    # The output is a subset of the input and contains no duplicates.
    assert set(result).issubset(set(paths))
    assert len(result) == len(set(result))
