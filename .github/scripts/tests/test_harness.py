"""Sanity checks for the Task 1 scaffold and test harness.

Confirms the logic-core module is importable, exposes the four placeholder
pure functions, and that the Hypothesis profile enforces the 100-example
minimum required by the design. These are replaced/augmented by the real
property and unit tests in tasks 2-6.
"""

from __future__ import annotations

from hypothesis import settings

import detect_leaves


def test_module_exposes_pure_functions():
    for name in ("filter_leaves", "parse_leaf", "build_matrix", "classify_source"):
        assert callable(getattr(detect_leaves, name)), name


def test_hypothesis_profile_enforces_minimum_examples():
    assert settings().max_examples >= 100
