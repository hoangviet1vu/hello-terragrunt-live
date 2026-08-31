"""Property test for matrix cap enforcement in ``build_matrix``.

Covers design Property 6: for any list of changed file paths that yields more
than 256 matched leaf units, the matrix builder signals an error (raises
:class:`detect_leaves.MatrixSizeExceededError`, a ``ValueError`` subclass) and
emits no matrix, rather than producing a partial or oversized matrix. Inputs at
and below the cap (256) succeed and produce exactly that many entries.

Validates: Requirements 5.3
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

import detect_leaves

from detect_leaves import MAX_MATRIX_SIZE  # 256, the GitHub Actions matrix cap


def _distinct_leaves(count: int) -> list[str]:
    """Build ``count`` distinct, well-formed leaf-unit paths.

    Paths are unique so ``filter_leaves`` de-duplication does not reduce the
    matched count below ``count`` -- the number of matched leaves is exactly
    ``count``. Using ``t{i}/e{i}/terragrunt.hcl`` keeps every segment within the
    leaf regex alphabet (``[A-Za-z0-9]+``).
    """
    return [f"t{i}/e{i}/terragrunt.hcl" for i in range(count)]


# Sizes clustered around the 256 boundary. Each range spans well over 100
# distinct values so Hypothesis can draw the full min-100 iterations without
# exhausting the input space:
#   - below/at the cap: 156..256 (101 sizes, all of which must succeed);
#   - above the cap: 257..457 (201 sizes, all of which must error).
_at_or_below_cap = st.integers(min_value=MAX_MATRIX_SIZE - 100, max_value=MAX_MATRIX_SIZE)
_above_cap = st.integers(min_value=MAX_MATRIX_SIZE + 1, max_value=MAX_MATRIX_SIZE + 200)


# Feature: terragrunt-pr-merge-workflow, Property 6: matrix cap enforcement
# For any list of changed file paths that yields more than 256 matched leaf
# units, build_matrix signals an error (non-zero / raises) and emits no matrix,
# rather than producing a partial or oversized matrix.
# Validates: Requirements 5.3
@given(count=_above_cap)
def test_property_over_cap_signals_error_and_emits_no_matrix(count):
    paths = _distinct_leaves(count)

    with pytest.raises(detect_leaves.MatrixSizeExceededError) as exc_info:
        build_result = detect_leaves.build_matrix(paths)  # noqa: F841

    # The error is a ValueError subclass and carries a cap-exceeded message.
    assert isinstance(exc_info.value, ValueError)
    assert "maximum matrix size exceeded" in str(exc_info.value).lower()


# Feature: terragrunt-pr-merge-workflow, Property 6: matrix cap enforcement
# Inputs at or just below the cap (255, 256) succeed and produce exactly one
# entry per matched leaf, confirming the boundary itself is inclusive.
# Validates: Requirements 5.3
@given(count=_at_or_below_cap)
def test_property_at_or_below_cap_succeeds(count):
    paths = _distinct_leaves(count)

    entries, has_units = detect_leaves.build_matrix(paths)

    assert has_units is True
    assert len(entries) == count
    assert count <= MAX_MATRIX_SIZE


# Explicit boundary check at exactly 255, 256, and 257 so the cap edge is
# pinned by concrete examples in addition to the generated ranges above.
@pytest.mark.parametrize(
    ("count", "should_raise"),
    [(255, False), (256, False), (257, True)],
)
def test_matrix_cap_boundary_examples(count, should_raise):
    paths = _distinct_leaves(count)

    if should_raise:
        with pytest.raises(detect_leaves.MatrixSizeExceededError):
            detect_leaves.build_matrix(paths)
    else:
        entries, has_units = detect_leaves.build_matrix(paths)
        assert has_units is True
        assert len(entries) == count
