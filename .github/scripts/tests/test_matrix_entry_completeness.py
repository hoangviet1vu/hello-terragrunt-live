"""Property test for ``build_matrix`` entry completeness (design Property 4).

Covers design Property 4 (entry completeness): for any list of changed file
paths, every entry in the emitted matrix has a non-empty ``tenant``, a
non-empty ``workDir``, and a non-empty ``leafPath``.

Validates: Requirements 5.5, 5.6
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
    max_size=6,
)


@st.composite
def _valid_leaf(draw):
    """A well-formed leaf unit path: ``<tenant>/<env>/terragrunt.hcl``."""
    return f"{draw(_segment)}/{draw(_segment)}/terragrunt.hcl"


@st.composite
def _near_miss_root(draw):
    """A root-config-ish path that must never produce a matrix entry."""
    kind = draw(st.integers(min_value=0, max_value=3))
    if kind == 0:
        return "root.hcl"  # repo-root root.hcl
    if kind == 1:
        return f"{draw(_segment)}/root.hcl"  # root.hcl one level down
    if kind == 2:
        return f"{draw(_segment)}/{draw(_segment)}/root.hcl"  # leaf-depth root.hcl
    return "terragrunt.hcl"  # repo-root terragrunt.hcl


@st.composite
def _deep_path(draw):
    """A too-deep path (4+ segments) that must never produce a matrix entry."""
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
            st.builds(lambda a, b: f"{a}/{b}/main.tf", _segment, _segment),
            st.builds(lambda a: f"{a}/de-v/terragrunt.hcl", _segment),
            st.builds(lambda a: f"ten_ant/{a}/terragrunt.hcl", _segment),
        )
    )


# A mixed path list drawing from every category above, kept well under the 256
# matrix cap so build_matrix returns entries rather than signalling an error.
_mixed_paths = st.lists(
    st.one_of(
        _valid_leaf(),
        _near_miss_root(),
        _deep_path(),
        _malformed_path(),
    ),
    max_size=40,
)


# Feature: terragrunt-pr-merge-workflow, Property 4: entry completeness
#
# For any list of changed file paths, every entry in the emitted matrix has a
# non-empty tenant, a non-empty workDir, and a non-empty leafPath.
#
# Validates: Requirements 5.5, 5.6
@given(paths=_mixed_paths)
def test_property4_entry_completeness(paths):
    entries, has_units = detect_leaves.build_matrix(paths)

    # has_units is True iff there is at least one entry.
    assert has_units == (len(entries) > 0)

    for entry in entries:
        # Each of the three fan-out fields must be present and non-empty so the
        # provision job always receives leafPath, tenant, and workDir.
        for field in ("tenant", "workDir", "leafPath"):
            assert field in entry, f"missing field {field!r} in {entry!r}"
            value = entry[field]
            assert isinstance(value, str)
            assert value != "", f"empty field {field!r} in {entry!r}"
