"""Unit tests for the ``detect_leaves`` CLI entry point (stdin -> stdout).

Exercises ``main(argv, stdin, stdout, stderr)`` end-to-end with in-memory
streams (``io.StringIO``), asserting the emitted GITHUB_OUTPUT-compatible
``matrix`` / ``has_units`` lines and the process exit code for the
representative input shapes: empty input, a single leaf, multiple leaves,
only-root (no matches), and an over-cap change set (>256 leaves).

These are example-based unit tests complementing the property tests that cover
the pure functions; here the focus is the CLI wiring (stream reading, output
formatting, and exit-code / stderr behavior).

Validates: Requirements 2.4, 2.5, 3.4, 5.1, 5.2, 5.3, 5.4
"""

from __future__ import annotations

import io
import json

import detect_leaves


def _run(stdin_text: str):
    """Invoke ``main`` with in-memory streams and return (exit_code, out, err)."""
    stdin = io.StringIO(stdin_text)
    stdout = io.StringIO()
    stderr = io.StringIO()
    code = detect_leaves.main(
        argv=[], stdin=stdin, stdout=stdout, stderr=stderr
    )
    return code, stdout.getvalue(), stderr.getvalue()


def _parse_outputs(stdout_text: str) -> dict:
    """Parse the ``key=value`` GITHUB_OUTPUT lines into a dict."""
    outputs = {}
    for line in stdout_text.splitlines():
        if not line:
            continue
        key, _, value = line.partition("=")
        outputs[key] = value
    return outputs


def test_empty_input_emits_empty_matrix_and_exit_zero():
    # Completely empty stdin -> no leaves, empty matrix, has_units=false, exit 0.
    # (Req 2.5, 3.4, 5.4)
    code, out, err = _run("")

    assert code == 0
    assert err == ""
    outputs = _parse_outputs(out)
    assert json.loads(outputs["matrix"]) == []
    assert outputs["has_units"] == "false"


def test_blank_lines_only_treated_as_empty():
    # Whitespace / blank lines (e.g. a trailing newline) yield no spurious path.
    # (Req 2.5, 3.4, 5.4)
    code, out, err = _run("\n   \n\n")

    assert code == 0
    assert err == ""
    outputs = _parse_outputs(out)
    assert json.loads(outputs["matrix"]) == []
    assert outputs["has_units"] == "false"


def test_single_leaf_emits_one_entry_and_exit_zero():
    # Exactly one leaf unit -> one matrix entry, has_units=true, exit 0.
    # (Req 5.1, 5.5)
    code, out, err = _run("SAMPLETENANT/dev/terragrunt.hcl\n")

    assert code == 0
    assert err == ""
    outputs = _parse_outputs(out)
    matrix = json.loads(outputs["matrix"])
    assert matrix == [
        {
            "tenant": "SAMPLETENANT",
            "envDir": "dev",
            "workDir": "SAMPLETENANT/dev",
            "leafPath": "SAMPLETENANT/dev/terragrunt.hcl",
        }
    ]
    assert outputs["has_units"] == "true"


def test_multiple_leaves_emit_one_entry_each_in_order():
    # Multiple distinct leaves -> one entry each, input order preserved.
    # (Req 5.2, 5.5)
    stdin_text = (
        "PRDCV/dev/terragrunt.hcl\n"
        "PRDCV/prod/terragrunt.hcl\n"
        "SAMPLETENANT/dev/terragrunt.hcl\n"
    )
    code, out, err = _run(stdin_text)

    assert code == 0
    assert err == ""
    outputs = _parse_outputs(out)
    matrix = json.loads(outputs["matrix"])
    assert [e["leafPath"] for e in matrix] == [
        "PRDCV/dev/terragrunt.hcl",
        "PRDCV/prod/terragrunt.hcl",
        "SAMPLETENANT/dev/terragrunt.hcl",
    ]
    assert [e["workDir"] for e in matrix] == [
        "PRDCV/dev",
        "PRDCV/prod",
        "SAMPLETENANT/dev",
    ]
    assert outputs["has_units"] == "true"


def test_only_root_paths_emit_empty_matrix_and_exit_zero():
    # A change set of only excluded/root paths matches zero leaves: the workflow
    # succeeds with an empty matrix and runs no provision job. (Req 2.4, 3.4, 5.4)
    stdin_text = (
        "root.hcl\n"
        "terragrunt.hcl\n"
        "SAMPLETENANT/root.hcl\n"
        "README.md\n"
    )
    code, out, err = _run(stdin_text)

    assert code == 0
    assert err == ""
    outputs = _parse_outputs(out)
    assert json.loads(outputs["matrix"]) == []
    assert outputs["has_units"] == "false"


def test_over_cap_input_fails_with_error_and_no_matrix():
    # More than 256 leaf units -> exit non-zero, a ::error:: annotation on
    # stderr, and no matrix emitted on stdout. (Req 5.3)
    leaves = "".join(f"T{i}/dev/terragrunt.hcl\n" for i in range(257))
    code, out, err = _run(leaves)

    assert code == 1
    assert out == ""
    assert "::error::" in err
    assert "maximum matrix size exceeded" in err


def test_at_cap_input_succeeds():
    # Exactly 256 leaf units is within the cap -> success with 256 entries.
    # (boundary complement to the >256 case; Req 5.2, 5.3)
    leaves = "".join(f"T{i}/dev/terragrunt.hcl\n" for i in range(256))
    code, out, err = _run(leaves)

    assert code == 0
    assert err == ""
    outputs = _parse_outputs(out)
    matrix = json.loads(outputs["matrix"])
    assert len(matrix) == 256
    assert outputs["has_units"] == "true"
