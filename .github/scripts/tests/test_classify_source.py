"""Tests for ``classify_source`` (Source_Scheme classifier).

Covers the pure-logic classification of a Terragrunt ``source`` string into
``"https"``, ``"ssh"``, or ``"unrecognized"`` based only on its transport
prefix (Requirement 9.1, design Property 7).
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import detect_leaves

# --- Unit / example tests ---------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        "git::https://github.com/hoangviet1vu/hello-terragrunt-modules.git//?ref=v1.0.0",
        "git::https://github.com/o/r.git",
        "git::https://gitlab.example.com/group/repo.git//module?ref=main",
        "git::https://",
    ],
)
def test_https_sources_classified_as_https(source):
    assert detect_leaves.classify_source(source) == "https"


@pytest.mark.parametrize(
    "source",
    [
        "git::git@github.com:hoangviet1vu/hello-terragrunt-modules.git//?ref=v1.0.0",
        "git::git@github.com:o/r.git",
        "git::ssh://git@github.com/o/r.git//module?ref=v2.3.4",
        "git::git@",
        "git::ssh://",
    ],
)
def test_ssh_sources_classified_as_ssh(source):
    assert detect_leaves.classify_source(source) == "ssh"


@pytest.mark.parametrize(
    "source",
    [
        "",
        "https://github.com/o/r.git",  # missing git:: prefix
        "git@github.com:o/r.git",  # missing git:: prefix
        "github.com/o/r",
        "git::http://github.com/o/r.git",  # http, not https
        "git::file:///local/path",
        "  git::https://github.com/o/r.git",  # leading whitespace
        "GIT::HTTPS://github.com/o/r.git",  # wrong case
        "registry.terraform.io/foo/bar",
    ],
)
def test_unrecognized_sources(source):
    assert detect_leaves.classify_source(source) == "unrecognized"


# --- Property-based test ----------------------------------------------------
# Feature: terragrunt-pr-merge-workflow, Property 7: For any Terragrunt source
# string, the classifier maps it to "https" when it begins with git::https://,
# to "ssh" when it begins with git::git@ or git::ssh://, and otherwise reports
# it as unrecognized -- the classification depends only on the transport prefix
# and never on the repository, path, or ?ref= portion.
# Validates: Requirements 9.1

# Arbitrary trailing content: repository, path, and ?ref= portions must not
# affect classification.
_tail = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=60,
)


@given(tail=_tail)
def test_property_https_prefix_maps_to_https(tail):
    assert detect_leaves.classify_source("git::https://" + tail) == "https"


@given(tail=_tail)
def test_property_ssh_git_at_prefix_maps_to_ssh(tail):
    assert detect_leaves.classify_source("git::git@" + tail) == "ssh"


@given(tail=_tail)
def test_property_ssh_scheme_prefix_maps_to_ssh(tail):
    assert detect_leaves.classify_source("git::ssh://" + tail) == "ssh"


@given(source=st.text(max_size=80))
def test_property_classification_matches_prefix(source):
    result = detect_leaves.classify_source(source)
    if source.startswith("git::https://"):
        assert result == "https"
    elif source.startswith("git::git@") or source.startswith("git::ssh://"):
        assert result == "ssh"
    else:
        assert result == "unrecognized"
    # Result is always one of the three permitted labels.
    assert result in {"https", "ssh", "unrecognized"}


# --- Dedicated Property 7 test ----------------------------------------------
# Feature: terragrunt-pr-merge-workflow, Property 7: source scheme classification
#
# For any Terragrunt source string the classifier maps it to "https" when it
# begins with git::https://, to "ssh" when it begins with git::git@ or
# git::ssh://, and otherwise reports it as unrecognized -- the classification
# depends only on the transport prefix and never on the repository, path, or
# ?ref= portion.
#
# This test builds git:: sources by varying the repository, path, and ?ref=
# portions independently of the transport prefix, then asserts the label is a
# pure function of the prefix. It also mixes in non-git strings to cover the
# unrecognized branch.
#
# **Validates: Requirements 9.1**

# Host segment, e.g. "github.com", "gitlab.example.com".
_hosts = st.sampled_from(
    ["github.com", "gitlab.example.com", "bitbucket.org", "git.internal.corp"]
)

# Repository owner/name pairs -- the "repo" portion that must not affect the label.
_repos = st.builds(
    lambda owner, name: f"{owner}/{name}",
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=1, max_size=20),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_", min_size=1, max_size=20),
)

# Optional in-repo module path following "//" -- the "path" portion.
_subpaths = st.one_of(
    st.just(""),
    st.builds(
        lambda p: "//" + p,
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789/-_",
            min_size=0,
            max_size=30,
        ),
    ),
)

# Optional ?ref= portion (tag, branch, or SHA) -- the "ref" portion.
_refs = st.one_of(
    st.just(""),
    st.builds(
        lambda r: "?ref=" + r,
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-_",
            min_size=1,
            max_size=20,
        ),
    ),
)


@st.composite
def _git_sources(draw):
    """Build a git:: source string with an explicit transport prefix.

    Returns ``(source, expected_label)`` where ``expected_label`` is derived
    solely from the chosen transport prefix. The repo/path/ref portions vary
    independently and must not change the expected label.
    """
    host = draw(_hosts)
    repo = draw(_repos)
    subpath = draw(_subpaths)
    ref = draw(_refs)

    scheme = draw(st.sampled_from(["https", "git@", "ssh://"]))
    if scheme == "https":
        source = f"git::https://{host}/{repo}.git{subpath}{ref}"
        expected = "https"
    elif scheme == "git@":
        source = f"git::git@{host}:{repo}.git{subpath}{ref}"
        expected = "ssh"
    else:  # ssh://
        source = f"git::ssh://git@{host}/{repo}.git{subpath}{ref}"
        expected = "ssh"
    return source, expected


# Non-git strings that must classify as "unrecognized": these deliberately lack
# any recognized git:: transport prefix.
_non_git_sources = st.one_of(
    st.just(""),
    st.builds(lambda s: "https://" + s, st.text(max_size=40)),  # no git:: prefix
    st.builds(lambda s: "git@" + s, st.text(max_size=40)),  # no git:: prefix
    st.builds(lambda s: "git::http://" + s, st.text(max_size=40)),  # http, not https
    st.builds(lambda s: "git::file://" + s, st.text(max_size=40)),
    st.builds(lambda s: "registry.terraform.io/" + s, st.text(max_size=40)),
    st.text(max_size=40).filter(
        lambda s: not (
            s.startswith("git::https://")
            or s.startswith("git::git@")
            or s.startswith("git::ssh://")
        )
    ),
)


@given(data=_git_sources())
@settings(max_examples=200)
def test_property7_git_source_scheme_depends_only_on_prefix(data):
    """git:: sources classify by transport prefix, independent of repo/path/ref."""
    source, expected = data
    assert detect_leaves.classify_source(source) == expected


@given(source=_non_git_sources)
@settings(max_examples=200)
def test_property7_non_git_sources_are_unrecognized(source):
    """Strings without a recognized git:: transport prefix are unrecognized."""
    assert detect_leaves.classify_source(source) == "unrecognized"
