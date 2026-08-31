"""Offline integration / smoke harness for the detect stage (Task 13.1).

This exercises the *first-parent* change-detection path end-to-end, matching
how the workflow's ``detect`` job computes the change set:

    git diff --name-only --diff-filter=AM "$MERGE_SHA^1" "$MERGE_SHA"
        | python3 .github/scripts/detect_leaves.py

Rather than mock git, we build a throwaway git repository on disk containing a
real merge commit whose feature branch adds/modifies leaf units (plus
near-miss and excluded files, plus a deletion and a rename to prove
``--diff-filter=AM`` drops them). We then run the exact first-parent diff the
workflow uses and feed it into ``detect_leaves.main``, asserting the emitted
matrix and ``has_units`` output.

Everything here is fully offline: no network, no credentials, no terragrunt.
The terragrunt ``plan`` dry-run path (backend / module-auth / working-directory
confirmation) lives in ``terragrunt_plan_dryrun.sh`` and is intentionally not
run here because it needs live credentials and private-module access.

Validates: Requirements 3.1, 3.3
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import detect_leaves

FIXTURES = Path(__file__).parent / "fixtures"
HTTPS_LEAF = FIXTURES / "leaves" / "https_source" / "terragrunt.hcl"
SSH_LEAF = FIXTURES / "leaves" / "ssh_source" / "terragrunt.hcl"

# Skip the whole module if git is not on PATH (the harness is git-driven).
pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is required for the detect integration harness"
)


def _git(repo: Path, *args: str) -> str:
    """Run a git command inside ``repo`` with a deterministic identity."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.com",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.com",
        # Keep the harness hermetic regardless of the developer's git config.
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _write(repo: Path, rel: str, content: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def _run_detect(diff_lines: list[str]) -> tuple[list[dict], bool, int]:
    """Pipe newline-delimited paths through detect_leaves.main (as the workflow does)."""
    stdin = io.StringIO("\n".join(diff_lines) + ("\n" if diff_lines else ""))
    stdout = io.StringIO()
    stderr = io.StringIO()
    rc = detect_leaves.main(stdin=stdin, stdout=stdout, stderr=stderr)

    matrix: list[dict] = []
    has_units = False
    for line in stdout.getvalue().splitlines():
        if line.startswith("matrix="):
            matrix = json.loads(line[len("matrix=") :])
        elif line.startswith("has_units="):
            has_units = line[len("has_units=") :] == "true"
    return matrix, has_units, rc


def _build_merge_repo(tmp_path: Path) -> tuple[Path, str]:
    """Create a repo with a base commit and a feature branch merged via a merge commit.

    Returns ``(repo_path, merge_sha)``. The merge commit has two parents; its
    first parent (``^1``) is the base ``main`` commit, so the first-parent diff
    yields exactly what the feature branch changed.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")

    https_content = HTTPS_LEAF.read_text()
    ssh_content = SSH_LEAF.read_text()

    # --- base commit on main -------------------------------------------------
    # PRDCV/dev exists at base so the feature branch can *modify* it (type M),
    # and a couple of files exist so the feature branch can delete / rename them
    # to prove --diff-filter=AM excludes D and R changes.
    _write(repo, "root.hcl", "# root\n")
    _write(repo, "PRDCV/dev/terragrunt.hcl", https_content)
    # OLDTENANT is deleted on the feature branch. Give it content unlike the
    # added NEWCV leaf so git does not pair the delete+add as a rename.
    _write(repo, "OLDTENANT/dev/terragrunt.hcl", "# deleted-leaf\n" + https_content)
    # RENAMEME is renamed on the feature branch; unique content keeps git's
    # rename detection pairing it only with its own renamed destination.
    _write(repo, "RENAMEME/dev/terragrunt.hcl", "# renamed-leaf\n" + ssh_content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    main_sha = _git(repo, "rev-parse", "HEAD").strip()

    # --- feature branch -------------------------------------------------------
    _git(repo, "checkout", "-q", "-b", "feature")

    # Added leaf unit (type A) -> should appear in the matrix. Give it content
    # distinct from any base-commit file so git rename detection does not pair
    # it with the deleted OLDTENANT leaf and reclassify the pair as a rename.
    _write(repo, "NEWCV/prod/terragrunt.hcl", "# added-new-leaf\n" + ssh_content)
    # Modified existing leaf unit (type M) -> should appear in the matrix.
    _write(repo, "PRDCV/dev/terragrunt.hcl", https_content + "\n# modified\n")

    # Excluded near-misses that must NOT appear:
    _write(repo, "root.hcl", "# root changed\n")  # root.hcl at repo root
    _write(repo, "PRDCV/prod/root.hcl", "# nested root\n")  # root.hcl nested
    _write(repo, "terragrunt.hcl", "# top-level tg\n")  # repo-root terragrunt.hcl
    _write(repo, "a/b/c/terragrunt.hcl", "# too deep\n")  # deep path
    _write(repo, "PRDCV/dev/README.md", "# not a leaf\n")  # wrong filename

    # Deleted leaf unit (type D) -> excluded by --diff-filter=AM.
    (repo / "OLDTENANT" / "dev" / "terragrunt.hcl").unlink()

    # Renamed leaf unit (rename-away, type R) -> excluded by --diff-filter=AM.
    # git mv does not create the destination directory, so make it first.
    (repo / "RENAMED" / "dev").mkdir(parents=True, exist_ok=True)
    _git(
        repo,
        "mv",
        "RENAMEME/dev/terragrunt.hcl",
        "RENAMED/dev/terragrunt.hcl",
    )

    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feature changes")

    # --- merge feature into main with a merge commit (first parent == main) --
    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "Merge PR", "feature")
    merge_sha = _git(repo, "rev-parse", "HEAD").strip()

    # Sanity: the merge commit's first parent is the pre-merge main tip.
    assert _git(repo, "rev-parse", f"{merge_sha}^1").strip() == main_sha
    return repo, merge_sha


def _first_parent_diff(repo: Path, merge_sha: str) -> list[str]:
    """Run the exact first-parent diff the workflow's detect job uses."""
    out = _git(
        repo,
        "diff",
        "--name-only",
        "--diff-filter=AM",
        f"{merge_sha}^1",
        merge_sha,
    )
    return [line for line in out.splitlines() if line.strip()]


def test_first_parent_diff_into_detect_yields_expected_matrix(tmp_path):
    """End-to-end: merge commit -> first-parent AM diff -> detect_leaves -> matrix.

    Confirms the added and modified leaf units are detected while root config,
    top-level terragrunt.hcl, deep paths, wrong filenames, deletions, and
    renamed-away files are all excluded.

    Validates: Requirements 3.1, 3.3
    """
    repo, merge_sha = _build_merge_repo(tmp_path)

    changed = _first_parent_diff(repo, merge_sha)

    # The AM diff itself must already drop the deletion and the rename-away
    # source (Req 3.3, enforced by git via --diff-filter=AM).
    assert "OLDTENANT/dev/terragrunt.hcl" not in changed  # deleted
    assert "RENAMEME/dev/terragrunt.hcl" not in changed  # renamed away

    matrix, has_units, rc = _run_detect(changed)

    assert rc == 0
    assert has_units is True

    work_dirs = sorted(entry["workDir"] for entry in matrix)
    assert work_dirs == ["NEWCV/prod", "PRDCV/dev"]

    by_workdir = {entry["workDir"]: entry for entry in matrix}
    assert by_workdir["NEWCV/prod"]["tenant"] == "NEWCV"
    assert by_workdir["NEWCV/prod"]["leafPath"] == "NEWCV/prod/terragrunt.hcl"
    assert by_workdir["PRDCV/dev"]["tenant"] == "PRDCV"
    assert by_workdir["PRDCV/dev"]["leafPath"] == "PRDCV/dev/terragrunt.hcl"

    # No excluded near-miss leaked into the matrix.
    all_leaf_paths = {entry["leafPath"] for entry in matrix}
    for excluded in (
        "root.hcl",
        "PRDCV/prod/root.hcl",
        "terragrunt.hcl",
        "a/b/c/terragrunt.hcl",
        "PRDCV/dev/README.md",
        "RENAMED/dev/terragrunt.hcl",
    ):
        assert excluded not in all_leaf_paths


def test_root_only_merge_yields_empty_matrix(tmp_path):
    """A merge touching only root.hcl produces an empty matrix / has_units=false.

    Mirrors the design's "only root.hcl PR -> empty matrix" smoke case (2.4)
    over the first-parent diff path.

    Validates: Requirements 3.1, 3.3
    """
    repo = tmp_path / "root_only"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _write(repo, "root.hcl", "# root\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")

    _git(repo, "checkout", "-q", "-b", "feature")
    _write(repo, "root.hcl", "# root changed\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "touch root only")

    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "-m", "Merge PR", "feature")
    merge_sha = _git(repo, "rev-parse", "HEAD").strip()

    changed = _first_parent_diff(repo, merge_sha)
    matrix, has_units, rc = _run_detect(changed)

    assert rc == 0
    assert has_units is False
    assert matrix == []


def test_fixture_leaves_classify_to_expected_schemes():
    """The two fixture leaves cover both auth paths (SSH + HTTPS).

    Ties the fixtures to the Source_Scheme classifier so the SSH/HTTPS
    auth-path coverage the plan dry-run harness relies on is asserted offline.

    Validates: Requirements 3.1
    """
    def source_of(leaf: Path) -> str:
        for line in leaf.read_text().splitlines():
            if "git::" in line:
                # Extract the git::... token between quotes.
                start = line.index("git::")
                end = line.index('"', start)
                return line[start:end]
        raise AssertionError(f"no git:: source in {leaf}")

    assert detect_leaves.classify_source(source_of(HTTPS_LEAF)) == "https"
    assert detect_leaves.classify_source(source_of(SSH_LEAF)) == "ssh"
