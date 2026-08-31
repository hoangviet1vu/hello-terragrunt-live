"""Static-analysis checks over the workflow and its shell helpers (Task 12.2).

The provision-on-merge workflow is predominantly declarative CI/IaC plumbing.
Two of its guarantees are not exercised by the logic-core property/unit tests
and are instead enforced here by static inspection of the committed source
(design "Testing Strategy" -> "Static grep checks", and "Secret safety"):

  1. Apply-flag presence (Req 10.4): the terragrunt apply invocation must run
     non-interactively with automatic approval, i.e. both ``-auto-approve`` and
     ``-input=false`` must appear in the apply command. The invocation lives in
     ``init_apply_gate.sh`` (the gate helper the workflow wires in); the flags
     are also asserted to be present somewhere in the checked source.

  2. Secret hygiene (Req 8.6, 9.7): no ``echo`` / ``cat`` / ``printf`` statement
     may print the *raw value* of a secret env var (``TOKEN``, ``SECURITY_KEY``,
     or any ``AWS_*`` secret) to stdout, where it would land in job logs. This
     is a discipline check on top of GitHub's automatic secret masking.

     Nuance encoded here (design "Secret safety"): passing secrets via ``env:``
     and using them as command *arguments* (e.g. ``git config`` credential
     rewrite) is allowed, and writing a secret to a *file* is allowed
     (``printf '%s\n' "$SECURITY_KEY" > ~/.ssh/id_ed25519``). What is forbidden
     is emitting the secret's value to stdout/stderr via ``echo``/``printf``
     with no redirection, or ``cat``-ing it. The forbidden-pattern detector
     therefore ignores ``printf``/``echo`` lines that redirect to a file.

These are pure source-inspection tests: they read the committed workflow and
``*.sh`` helpers and never execute them.

Validates: Requirements 8.6, 9.7, 10.4
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths under inspection.
# ---------------------------------------------------------------------------
# tests/ -> scripts/ -> .github/ -> repo root
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_GITHUB_DIR = _SCRIPTS_DIR.parent
_REPO_ROOT = _GITHUB_DIR.parent

_WORKFLOW = _GITHUB_DIR / "workflows" / "provision-on-merge.yml"
_INIT_APPLY_GATE = _SCRIPTS_DIR / "init_apply_gate.sh"

# All shell helpers that make up the provision steps. New helpers dropped into
# .github/scripts are picked up automatically so the hygiene check keeps pace.
_SHELL_HELPERS = sorted(_SCRIPTS_DIR.glob("*.sh"))

# The secret env vars whose raw values must never reach stdout. AWS_* is matched
# as a family so a future AWS_SESSION_TOKEN (etc.) is covered too.
_SECRET_NAMES = ("TOKEN", "SECURITY_KEY")
_SECRET_PREFIXES = ("AWS_",)


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------
def _read(path: Path) -> str:
    assert path.is_file(), f"expected file to exist: {path}"
    return path.read_text(encoding="utf-8")


def _iter_source_lines(text: str):
    """Yield (lineno, stripped_line) for non-blank, non-comment lines.

    Full-line ``#`` comments are skipped so documentation that *describes* a
    forbidden pattern (as this very module's docstring and the helpers'
    header comments do) does not trip the detector.
    """
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        yield i, line


def _secret_var_alternation() -> str:
    """Regex alternation matching a secret env-var reference.

    Matches ``TOKEN``, ``SECURITY_KEY``, and any ``AWS_<UPPER>`` name, in either
    ``$NAME`` or ``${NAME}`` form.
    """
    names = list(_SECRET_NAMES)
    # AWS_* family: AWS_ followed by one or more uppercase/underscore chars.
    aws = r"AWS_[A-Z_]+"
    exact = "|".join(re.escape(n) for n in names)
    body = rf"(?:{exact}|{aws})"
    # $NAME or ${NAME}
    return rf"\$(?:{body}\b|\{{{body}\}})"


# Precompiled reference to "a secret variable" for reuse.
_SECRET_REF = _secret_var_alternation()

# A statement that prints a secret's value to stdout/stderr:
#   - echo ... $SECRET ...        (any echo mentioning the secret)
#   - printf ... $SECRET ...      (printf mentioning the secret)
#   - cat ... $SECRET ...         (cat of a secret-named target)
# We then EXCLUDE lines that redirect to a file (``>`` / ``>>`` to a non-fd
# target), because writing a secret to a file is allowed (Req 9.3 SSH key).
_PRINT_CMD = re.compile(
    rf"""^\s*
        (?:echo|printf|cat)     # a stdout-emitting command
        \b .*?                  # any intervening args/format string
        {_SECRET_REF}           # ... that references a secret var
    """,
    re.VERBOSE,
)

# Redirection to a file target (not a numeric fd like ``2>&1`` / ``>&2``).
# Presence of such a redirect means the output goes to a file, not the log.
_FILE_REDIRECT = re.compile(r">>?\s*(?![&0-9])\S")


def _forbidden_secret_prints(text: str):
    """Return a list of (lineno, line) that print a secret value to a log.

    A line is flagged when it runs echo/printf/cat referencing a secret var AND
    does not redirect that output to a file. Lines that redirect to a file
    (e.g. ``printf '%s\\n' "$SECURITY_KEY" > ~/.ssh/id_ed25519``) are allowed.
    """
    offenders = []
    for lineno, line in _iter_source_lines(text):
        if not _PRINT_CMD.search(line):
            continue
        if _FILE_REDIRECT.search(line):
            # Output is redirected to a file, not emitted to the log -> allowed.
            continue
        offenders.append((lineno, line))
    return offenders


# ---------------------------------------------------------------------------
# Apply-flag presence (Req 10.4).
# ---------------------------------------------------------------------------
def test_init_apply_gate_apply_has_auto_approve_and_input_false():
    """The terragrunt apply invocation carries -auto-approve and -input=false.

    The gate helper is where the apply command actually lives; assert the exact
    invocation line contains both non-interactive flags (Req 10.4).
    """
    text = _read(_INIT_APPLY_GATE)

    # Match the actual apply *invocation*, not an error-message string. The
    # invocation is a command whose program is the terragrunt binary -- either
    # literal ``terragrunt`` or the ``$tg`` / ``${tg}`` / ``"$tg"`` indirection
    # the gate uses -- appearing at the *start* of the command (optionally after
    # a shell control prefix like ``if !``), immediately followed by ``apply``.
    # Error strings such as ``err "terragrunt apply failed..."`` are excluded
    # because there ``terragrunt`` follows another command word (``err``) inside
    # a quoted string rather than starting the command.
    invocation = re.compile(
        r"""^\s*
            (?:(?:if\s+)?!?\s*)?              # optional `if ! ` control prefix
            (?:"?\$\{?(?:tg|TERRAGRUNT_BIN)\}?"?|terragrunt)  # the binary
            \s+apply\b
        """,
        re.VERBOSE,
    )
    apply_lines = [
        line for _, line in _iter_source_lines(text) if invocation.search(line)
    ]
    assert apply_lines, (
        "no terragrunt apply invocation found in init_apply_gate.sh"
    )

    for line in apply_lines:
        assert "-auto-approve" in line, (
            f"terragrunt apply invocation missing -auto-approve: {line!r}"
        )
        assert "-input=false" in line, (
            f"terragrunt apply invocation missing -input=false: {line!r}"
        )


def test_apply_flags_present_in_checked_source():
    """Both non-interactive apply flags appear in the workflow/helper source.

    Belt-and-suspenders over the previous test: search the workflow and every
    shell helper so the flags are guaranteed present in the committed source
    even if the apply invocation is relocated (Req 10.4).
    """
    corpus = _read(_WORKFLOW) + "\n"
    for helper in _SHELL_HELPERS:
        corpus += _read(helper) + "\n"

    assert "-auto-approve" in corpus, "-auto-approve not found in workflow/helpers"
    assert "-input=false" in corpus, "-input=false not found in workflow/helpers"


# ---------------------------------------------------------------------------
# Secret hygiene: no echo/cat/printf of secret values to logs (Req 8.6, 9.7).
# ---------------------------------------------------------------------------
def test_workflow_does_not_print_secret_values():
    """The workflow YAML never echoes/cats/printfs a secret var to stdout."""
    offenders = _forbidden_secret_prints(_read(_WORKFLOW))
    assert not offenders, (
        "workflow prints secret value(s) to the log: "
        + "; ".join(f"line {n}: {line}" for n, line in offenders)
    )


@pytest.mark.parametrize("helper", _SHELL_HELPERS, ids=lambda p: p.name)
def test_shell_helper_does_not_print_secret_values(helper: Path):
    """No .sh helper echoes/cats/printfs a secret var to stdout (Req 8.6, 9.7).

    Legitimate uses are allowed by construction: passing secrets as command
    arguments (git config) is not an echo/printf/cat, and writing a secret to a
    file (``printf ... "$SECURITY_KEY" > keyfile``) is excluded because it
    redirects to a file rather than the log.
    """
    offenders = _forbidden_secret_prints(_read(helper))
    assert not offenders, (
        f"{helper.name} prints secret value(s) to the log: "
        + "; ".join(f"line {n}: {line}" for n, line in offenders)
    )


# ---------------------------------------------------------------------------
# Self-check: the detector actually catches a forbidden pattern and permits the
# allowed file-write form. Guards against the hygiene tests silently passing
# because the regex never matches anything (Req 8.6, 9.7).
# ---------------------------------------------------------------------------
def test_detector_flags_direct_secret_echo():
    """A raw ``echo "$TOKEN"`` to stdout is detected as forbidden."""
    bad = 'echo "$TOKEN"'
    assert _forbidden_secret_prints(bad), "detector missed a direct secret echo"


def test_detector_flags_printf_secret_to_stdout():
    """``printf`` of a secret without redirection is detected as forbidden."""
    bad = 'printf "%s\\n" "${SECURITY_KEY}"'
    assert _forbidden_secret_prints(bad), "detector missed a printf of a secret"


def test_detector_flags_cat_of_aws_secret():
    """A ``cat`` referencing an AWS_* secret is detected as forbidden."""
    bad = 'cat "$AWS_SECRET_ACCESS_KEY"'
    assert _forbidden_secret_prints(bad), "detector missed a cat of an AWS secret"


def test_detector_allows_secret_write_to_file():
    """Writing a secret to a *file* (redirected) is permitted, not flagged."""
    ok = 'printf \'%s\\n\' "$SECURITY_KEY" > ~/.ssh/id_ed25519'
    assert not _forbidden_secret_prints(ok), (
        "detector wrongly flagged a secret file-write"
    )


def test_detector_allows_secret_as_command_argument():
    """Passing a secret as a git config argument is permitted, not flagged."""
    ok = 'git config --global "url.https://${TOKEN}@github.com/.insteadOf" "https://github.com/"'
    assert not _forbidden_secret_prints(ok), (
        "detector wrongly flagged a secret used as a command argument"
    )
