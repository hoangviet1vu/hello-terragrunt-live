"""Unit tests for the module-auth-by-scheme helper.

Exercises ``.github/scripts/configure_module_auth.sh`` end-to-end via
``subprocess`` with temporary leaf files and the script's testability env
hooks (``MODULE_AUTH_HOME``, ``MODULE_AUTH_SSH_DIR``, ``MODULE_AUTH_GIT``,
``MODULE_AUTH_KEYSCAN``). Each case creates a temp leaf ``terragrunt.hcl``
declaring an HTTPS or SSH ``git::`` source and asserts the auth handler's
behavior on the success and failure paths.

Cases (design "Auth handling" / Testing Strategy):
  - https-with-TOKEN        -> git config credential rewrite is invoked
  - ssh-with-SECURITY_KEY   -> 600-mode key file + known_hosts written
  - https-missing-TOKEN     -> exit non-zero, names TOKEN, no git config change
  - ssh-missing-SECURITY_KEY-> exit non-zero, names SECURITY_KEY, no key file
  - unrecognized scheme     -> exit non-zero, no change

On the failure paths the tests assert the script makes no configuration change
(no git invocation recorded, no SSH key written) and emits the correct error.
Success and failure paths also assert the raw secret values never appear in the
script's stdout/stderr (Req 9.7).

Validates: Requirements 9.2, 9.3, 9.4, 9.5
"""

from __future__ import annotations

import os
import stat
import subprocess
import textwrap

import pytest

# Absolute path to the script under test (sibling of the tests/ directory).
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AUTH_SCRIPT = os.path.join(_SCRIPTS_DIR, "configure_module_auth.sh")

# Sentinel secret values used to detect leakage into logs.
_FAKE_TOKEN = "ghp_FAKE_TOKEN_VALUE_1234567890"
_FAKE_SSH_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "FAKEKEYMATERIALdoesnotmatterforthistest\n"
    "-----END OPENSSH PRIVATE KEY-----"
)

_HTTPS_SOURCE = (
    'git::https://github.com/hoangviet1vu/hello-terragrunt-modules.git//?ref=v1.0.0'
)
_SSH_SOURCE = (
    'git::git@github.com:hoangviet1vu/hello-terragrunt-modules.git//?ref=v1.0.0'
)
_UNRECOGNIZED_SOURCE = (
    'git::ftp://example.com/hoangviet1vu/hello-terragrunt-modules.git//?ref=v1.0.0'
)


def _write_leaf(tmp_path, source: str):
    """Create a temp leaf terragrunt.hcl declaring the given git:: source."""
    leaf = tmp_path / "terragrunt.hcl"
    leaf.write_text(
        textwrap.dedent(
            f"""\
            include "root" {{
              path = find_in_parent_folders("root.hcl")
            }}

            terraform {{
              source = "{source}"
            }}

            inputs = {{
              tenant_name     = "SAMPLETENANT"
              environment     = "dev"
              enable_dynamodb = true
              enable_ecr      = false
            }}
            """
        )
    )
    return leaf


def _make_git_recorder(tmp_path):
    """Create a MODULE_AUTH_GIT stub that records its args to a file.

    Returns (git_cmd_path, record_file). The record file only exists after the
    stub has been invoked at least once, so its absence proves git was never
    called (i.e. no git configuration change was made).
    """
    record = tmp_path / "git_args.log"
    git_stub = tmp_path / "git_stub.sh"
    git_stub.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            # Record every argument (one per line) so the test can assert the
            # exact git invocation without executing real git.
            for a in "$@"; do
              printf '%s\\n' "$a" >> "{record}"
            done
            exit 0
            """
        )
    )
    git_stub.chmod(0o755)
    return str(git_stub), record


def _make_keyscan_stub(tmp_path):
    """Create a MODULE_AUTH_KEYSCAN stub emitting a fake known_hosts line."""
    keyscan = tmp_path / "keyscan_stub.sh"
    keyscan.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            printf 'github.com ssh-ed25519 AAAAFAKEHOSTKEY\\n'
            exit 0
            """
        )
    )
    keyscan.chmod(0o755)
    return str(keyscan)


def _run_auth(leaf_path, env_overrides):
    """Invoke the auth script with a controlled environment."""
    env = {
        # Keep a minimal, predictable environment; PATH is needed for bash and
        # the stub scripts' shebangs.
        "PATH": os.environ.get("PATH", ""),
        "LEAFPATH": str(leaf_path),
    }
    env.update(env_overrides)
    return subprocess.run(
        ["bash", _AUTH_SCRIPT],
        env=env,
        capture_output=True,
        text=True,
    )


def test_https_with_token_invokes_git_config_rewrite(tmp_path):
    # HTTPS source + TOKEN present -> git config credential URL rewrite invoked
    # via the MODULE_AUTH_GIT stub; success exit; secret not leaked to logs.
    # (Req 9.2)
    leaf = _write_leaf(tmp_path, _HTTPS_SOURCE)
    git_cmd, record = _make_git_recorder(tmp_path)

    result = _run_auth(
        leaf,
        {"TOKEN": _FAKE_TOKEN, "MODULE_AUTH_GIT": git_cmd},
    )

    assert result.returncode == 0, result.stderr
    # git was invoked exactly once for the config rewrite.
    assert record.exists(), "git config was not invoked"
    recorded = record.read_text()
    assert "config" in recorded
    assert "--global" in recorded
    # The insteadOf key targets github.com credential rewrite.
    assert "url.https://" in recorded
    assert ".insteadOf" in recorded
    assert "https://github.com/" in recorded
    # The raw token must not appear in the script's own stdout/stderr (Req 9.7).
    assert _FAKE_TOKEN not in result.stdout
    assert _FAKE_TOKEN not in result.stderr


def test_ssh_with_security_key_writes_key_600_and_known_hosts(tmp_path):
    # SSH source + SECURITY_KEY present -> key file written mode 600 and a
    # known_hosts entry produced via the MODULE_AUTH_KEYSCAN stub. (Req 9.3)
    leaf = _write_leaf(tmp_path, _SSH_SOURCE)
    ssh_dir = tmp_path / "ssh"
    keyscan = _make_keyscan_stub(tmp_path)

    result = _run_auth(
        leaf,
        {
            "SECURITY_KEY": _FAKE_SSH_KEY,
            "MODULE_AUTH_SSH_DIR": str(ssh_dir),
            "MODULE_AUTH_KEYSCAN": keyscan,
        },
    )

    assert result.returncode == 0, result.stderr

    key_file = ssh_dir / "id_ed25519"
    known_hosts = ssh_dir / "known_hosts"
    assert key_file.exists(), "SSH private key was not written"
    assert known_hosts.exists(), "known_hosts was not written"

    # Key file permissions must be exactly 600.
    mode = stat.S_IMODE(key_file.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    # Key content round-trips; known_hosts got the keyscan output.
    assert key_file.read_text().strip() == _FAKE_SSH_KEY.strip()
    assert "github.com" in known_hosts.read_text()

    # The raw key material must not appear in the script's logs (Req 9.7).
    assert _FAKE_SSH_KEY not in result.stdout
    assert _FAKE_SSH_KEY not in result.stderr


def test_https_missing_token_fails_names_token_and_no_git_change(tmp_path):
    # HTTPS source but TOKEN empty -> non-zero exit, error naming TOKEN, and no
    # git config change (the recorder file must not be created). (Req 9.4)
    leaf = _write_leaf(tmp_path, _HTTPS_SOURCE)
    git_cmd, record = _make_git_recorder(tmp_path)

    result = _run_auth(
        leaf,
        {"TOKEN": "", "MODULE_AUTH_GIT": git_cmd},
    )

    assert result.returncode != 0
    assert "TOKEN" in result.stderr
    # No git invocation happened -> no configuration change.
    assert not record.exists(), "git config should not have been invoked"


def test_ssh_missing_security_key_fails_names_key_and_no_key_written(tmp_path):
    # SSH source but SECURITY_KEY empty -> non-zero exit, error naming
    # SECURITY_KEY, and no key/known_hosts written. (Req 9.5)
    leaf = _write_leaf(tmp_path, _SSH_SOURCE)
    ssh_dir = tmp_path / "ssh"
    keyscan = _make_keyscan_stub(tmp_path)

    result = _run_auth(
        leaf,
        {
            "SECURITY_KEY": "",
            "MODULE_AUTH_SSH_DIR": str(ssh_dir),
            "MODULE_AUTH_KEYSCAN": keyscan,
        },
    )

    assert result.returncode != 0
    assert "SECURITY_KEY" in result.stderr
    # No key file and no known_hosts should have been written.
    assert not (ssh_dir / "id_ed25519").exists()
    assert not (ssh_dir / "known_hosts").exists()


def test_unrecognized_scheme_fails_and_makes_no_change(tmp_path):
    # An unrecognized transport prefix -> non-zero exit with an
    # "unrecognized source scheme" error and no git/SSH change. (Req 9.1 error
    # path; complements 9.2-9.5)
    leaf = _write_leaf(tmp_path, _UNRECOGNIZED_SOURCE)
    git_cmd, record = _make_git_recorder(tmp_path)
    ssh_dir = tmp_path / "ssh"
    keyscan = _make_keyscan_stub(tmp_path)

    result = _run_auth(
        leaf,
        {
            "TOKEN": _FAKE_TOKEN,
            "SECURITY_KEY": _FAKE_SSH_KEY,
            "MODULE_AUTH_GIT": git_cmd,
            "MODULE_AUTH_SSH_DIR": str(ssh_dir),
            "MODULE_AUTH_KEYSCAN": keyscan,
        },
    )

    assert result.returncode != 0
    assert "unrecognized source scheme" in result.stderr
    # No git invocation and no SSH artifacts.
    assert not record.exists(), "git config should not have been invoked"
    assert not (ssh_dir / "id_ed25519").exists()
    assert not (ssh_dir / "known_hosts").exists()
