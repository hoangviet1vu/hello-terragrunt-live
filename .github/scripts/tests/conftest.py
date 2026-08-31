"""Pytest / Hypothesis test harness configuration for the logic core.

Registers and loads a Hypothesis profile that enforces the design's minimum of
100 examples per property test (Testing Strategy). The profile is loaded at
import time so every property test in this directory inherits the setting.

It also ensures the parent ``.github/scripts`` directory is importable so tests
can ``import detect_leaves`` regardless of the invocation directory.
"""

from __future__ import annotations

import os
import sys

from hypothesis import HealthCheck, settings

# Make the sibling ``detect_leaves`` module importable.
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Minimum of 100 examples per property test, per design Testing Strategy.
settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ci")
