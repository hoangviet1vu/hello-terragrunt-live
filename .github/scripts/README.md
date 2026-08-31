# `.github/scripts`

Helper scripts backing the `provision-on-merge` GitHub Actions workflow
([`.github/workflows/provision-on-merge.yml`](../workflows/provision-on-merge.yml)).
This directory implements the design in
[`.kiro/specs/terragrunt-pr-merge-workflow/`](../../.kiro/specs/terragrunt-pr-merge-workflow)
(see `requirements.md` and `design.md` there for the full spec).

**In one sentence:** when a PR is merged into `main`, the workflow figures out
which `<TENANT>/<env>/terragrunt.hcl` "leaf" units changed, and runs
`terragrunt init` + `terragrunt apply` against each one, in its own job, bound
to the `dev` GitHub Environment.

## Table of Contents

- [1. What runs on GitHub Actions, and what each script does](#1-what-runs-on-github-actions-and-what-each-script-does)
  - [`detect` job](#detect-job)
  - [`provision` job (one instance per matrix entry, `fail-fast: false`)](#provision-job-one-instance-per-matrix-entry-fail-fast-false)
  - [`strategy.fail-fast: false` and aggregation](#strategyfail-fast-false-and-aggregation)
  - [Not wired into the workflow (manual/optional)](#not-wired-into-the-workflow-manualoptional)
  - [`.github/workflows/lint-actions.yml`](#githubworkflowslint-actionsyml)
- [2. Technical design of the Python code](#2-technical-design-of-the-python-code)
  - [2.1 Design principle: pure functions + a thin CLI shell](#21-design-principle-pure-functions--a-thin-cli-shell)
  - [2.2 `filter_leaves` — the path filter](#22-filter_leaves--the-path-filter)
  - [2.3 `parse_leaf` — the Path_Parser](#23-parse_leaf--the-path_parser)
  - [2.4 `build_matrix` — composition + the 256 cap](#24-build_matrix--composition--the-256-cap)
  - [2.5 `classify_source` — Source_Scheme classifier](#25-classify_source--source_scheme-classifier)
  - [2.6 CLI wrapper (`main`)](#26-cli-wrapper-main)
- [3. Building and running the tests](#3-building-and-running-the-tests)
  - [3.1 Layout](#31-layout)
  - [3.2 Set up a virtual environment](#32-set-up-a-virtual-environment)
  - [3.3 Run the tests](#33-run-the-tests)
  - [3.4 actionlint (workflow YAML, not Python)](#34-actionlint-workflow-yaml-not-python)
  - [3.5 What's *not* covered by `pytest`](#35-whats-not-covered-by-pytest)

---

## 1. What runs on GitHub Actions, and what each script does

The workflow has two jobs: `detect` (one run) and `provision` (fanned out,
one job per changed leaf). Below, steps are listed in execution order with
the script that backs them.

### `detect` job

| Step | Script | Purpose |
|------|--------|---------|
| Guard merged state | [`guard_merged_state.sh`](guard_merged_state.sh) | Reads `MERGED` (`github.event.pull_request.merged`). Exits `0` only for the literal strings `true`/`false`; anything else (empty, `null`, ...) is treated as an indeterminable payload and fails the run *before* any change detection, per Req 1.3/1.5. |
| Checkout (`fetch-depth: 0`) | *(built-in `actions/checkout`)* | Full history is required so the merge commit's first parent is present locally. |
| Compute changed leaf units | [`detect_leaves.py`](detect_leaves.py) | The workflow runs `git diff --name-only --diff-filter=AM "$MERGE_SHA^1" "$MERGE_SHA"` (added/modified files between the merge commit and its first parent) and pipes the result into this script's stdin. The script filters, parses, and caps the list, then writes `matrix=<json>` and `has_units=<true|false>` lines straight into `$GITHUB_OUTPUT`. |

If `git diff` itself fails (e.g. shallow history), the workflow step fails
directly with `::error::change detection could not be completed` — that path
never reaches Python.

### `provision` job (one instance per matrix entry, `fail-fast: false`)

Bound to `environment: dev`, so `${{ vars.* }}` / `${{ secrets.* }}` resolve
only from that GitHub Environment. Job-level `env:` exports
`TG_STATE_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
so every step — and `root.hcl`'s `get_env(...)` calls, and Terraform's AWS
provider — can see them.

| Step | Script | Purpose |
|------|--------|---------|
| Validate matrix entry | [`validate_entry.sh`](validate_entry.sh) | Fails the leg if `TENANT` / `WORKDIR` / `LEAFPATH` is empty, or if `LEAFPATH` doesn't have at least two directory segments before the filename (malformed path guard, Req 4.4/5.6). Runs before any Terragrunt or AWS call. |
| Validate secrets and vars | [`validate_secrets_vars.sh`](validate_secrets_vars.sh) | Confirms `TG_STATE_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` are all set and non-empty, failing on the *first* missing one by name (never by value). `TOKEN`/`SECURITY_KEY` are **not** checked here — only one of them is needed, depending on scheme, so that's deferred to the auth step. |
| Set up Terraform / Install Terragrunt | *(pinned versions, inline `run:`)* | Reproducible toolchain (Terraform `1.9.8`, Terragrunt `v0.67.4`). |
| Configure module auth | [`configure_module_auth.sh`](configure_module_auth.sh) | Reads the leaf's `terraform { source = "git::..." }` line, classifies it as `https` / `ssh` / `unrecognized`, and configures Git accordingly *before* `terragrunt init` ever runs. See §2.4 below. |
| Terragrunt init + apply | [`init_apply_gate.sh`](init_apply_gate.sh) | Runs with `working-directory: ${{ matrix.workDir }}` set by the workflow (this script does **not** `cd`). Runs `terragrunt init`; only on a zero exit does it run `terragrunt apply -auto-approve -input=false --terragrunt-non-interactive`. Any failure is reported as `::error::...failed for <tenant>/<env>`. |

Because `working-directory` changes the runner's cwd away from the repo
root, the workflow invokes this last script by its **absolute** path
(`$GITHUB_WORKSPACE/.github/scripts/init_apply_gate.sh`) — the other helpers
run from the repo root and don't need that.

### `strategy.fail-fast: false` and aggregation

One leg failing doesn't cancel its siblings — every leg runs to completion.
If *any* leg fails, GitHub reports the `provision` job (and thus the overall
run) as failed; if all legs succeed, the run succeeds. This is native GitHub
Actions matrix behavior, not scripted here.

### Not wired into the workflow (manual/optional)

[`terragrunt_plan_dryrun.sh`](terragrunt_plan_dryrun.sh) is a standalone,
**non-mutating** harness (`terragrunt init` + `terragrunt plan`, never
`apply`) for proving backend resolution, module auth, and working-directory
selection against a fixture leaf before trusting a real `apply` run. It
self-skips (exit `0`) when `terragrunt` or the required live
credentials/network aren't available, unless `TG_DRYRUN_STRICT=1`. See
[`tests/INTEGRATION_MANUAL.md`](tests/INTEGRATION_MANUAL.md) for how it's used
as a manual pre-flight check.

### `.github/workflows/lint-actions.yml`

A separate, always-on workflow that installs a pinned `actionlint` and lints
every workflow file (`pull_request`/`push` on changes under
`.github/workflows/**`). It catches YAML/expression/context errors and
structural regressions in `provision-on-merge.yml` (trigger, `if` gates,
`environment: dev`, matrix wiring, `fail-fast: false`) — this is separate
from, and complements, the pytest suite described below.

---

## 2. Technical design of the Python code

Only one file is Python: [`detect_leaves.py`](detect_leaves.py). Everything
else in the workflow is Bash, deliberately kept as thin, single-purpose
scripts (§1) so each has one obvious failure mode and no shared state.
`detect_leaves.py` is the exception because its behavior is **input-varying**
in a way that's worth property-testing (arbitrary changed-file lists), and
Bash isn't a good fit for that.

### 2.1 Design principle: pure functions + a thin CLI shell

The module is split into pure, side-effect-free functions and a small I/O
wrapper around them:

```
_LEAF_PATTERN            compiled regex: ^[A-Za-z0-9]+/[A-Za-z0-9]+/terragrunt\.hcl$

filter_leaves(paths)     -> list[str]        pure: keep only leaf-unit paths
parse_leaf(path)         -> dict             pure: derive tenant/envDir/workDir/leafPath
build_matrix(paths)      -> (entries, bool)  pure: filter_leaves + parse_leaf + 256 cap
classify_source(source)  -> str              pure: "https" | "ssh" | "unrecognized"

_read_paths(stream)       -> list[str]       I/O: stdin -> path list
_format_outputs(...)      -> str             I/O: entries -> GITHUB_OUTPUT text
main(argv, stdin, ...)    -> int             I/O: wires the above together
```

Every function that has input-dependent logic takes plain Python values in
and returns plain Python values out — no filesystem, no environment
variables, no subprocess calls. That's what makes them directly callable
from pytest/Hypothesis without mocking anything, and it mirrors the design
doc's "pure-logic core" split (path filter / Path_Parser / matrix builder /
Source_Scheme classifier all isolated from CI/Terragrunt plumbing).

### 2.2 `filter_leaves` — the path filter

Anchored regex match against `^[A-Za-z0-9]+/[A-Za-z0-9]+/terragrunt\.hcl$`.
Order is preserved and duplicates are dropped (first occurrence wins) using
an explicit `seen` set rather than, say, sorting — so the matrix's entry
order is deterministic and traceable back to `git diff`'s output order.

Anchoring is what does all the exclusion work for free:
- `root.hcl` never matches (wrong filename, any depth).
- A repo-root `terragrunt.hcl` never matches (no `<tenant>/<env>` prefix — a
  single segment fails the two-segment-plus-filename shape).
- Deeper paths (`a/b/c/terragrunt.hcl`) never match (too many segments).

### 2.3 `parse_leaf` — the Path_Parser

Splits on `/`. `tenant` = segment 0, `envDir` = segment 1 (carried for
reporting only — the design explicitly forbids validating environment
names), `workDir` = everything except the last segment (i.e. `leafPath`
minus `/terragrunt.hcl`). Raises `MalformedLeafPathError` (a `ValueError`
subclass) if there are fewer than 3 segments total. In practice
`filter_leaves` never lets a malformed path reach `parse_leaf`, but the
guard exists because `parse_leaf` is also callable directly, and the design
requires the *parser* — not just the filter — to defend against malformed
input (Req 4.4).

### 2.4 `build_matrix` — composition + the 256 cap

`filter_leaves` → (if empty, short-circuit `([], False)`) → cap check
against `MAX_MATRIX_SIZE = 256` (GitHub Actions' hard limit on matrix jobs
per run) → `parse_leaf` mapped over the survivors. Exceeding the cap raises
`MatrixSizeExceededError` instead of silently truncating or letting GitHub
reject the run opaquely later.

### 2.5 `classify_source` — Source_Scheme classifier

Pure prefix match, mirrored by the equivalent `case` statement in
[`configure_module_auth.sh`](configure_module_auth.sh) (which can't call
into Python — it runs before any Python is available in that step, and
keeping it as inline Bash keeps the auth step dependency-free). The two
implementations are kept in sync intentionally; a change to one must be
mirrored in the other. Classification depends **only** on the transport
prefix (`git::https://` → `https`; `git::git@` or `git::ssh://` → `ssh`;
anything else → `unrecognized`) — never on the repo path or `?ref=`
fragment.

### 2.6 CLI wrapper (`main`)

Reads newline-delimited paths from `stdin` (blank lines/whitespace
stripped, so an empty `git diff` yields `[]`, not `[""]`), calls
`build_matrix`, and either:
- writes `matrix=<compact-json>` + `has_units=<true|false>` to `stdout`
  (this is appended directly into `$GITHUB_OUTPUT` by the workflow step), or
- on `MatrixSizeExceededError`, prints `::error::...` to `stderr` and
  returns `1`, writing no output at all.

`stdin`/`stdout`/`stderr` are injectable parameters (default to
`sys.std*`), which is what lets `tests/test_cli.py` exercise `main()`
in-process with `io.StringIO()` instead of spawning a subprocess.

No third-party dependencies are used at runtime — only `json`, `re`, `sys`
from the standard library, so the workflow needs nothing beyond the
`python3` already present on `ubuntu-latest`.

---

## 3. Building and running the tests

### 3.1 Layout

```
.github/scripts/
├── detect_leaves.py         # the only script under test with pytest/Hypothesis
├── *.sh                     # bash helpers, covered by subprocess-driven pytest
├── pyproject.toml           # pytest config + documented Hypothesis floor
├── requirements-dev.txt     # pinned test deps: hypothesis==6.112.1, pytest==8.3.3
└── tests/
    ├── conftest.py          # registers the Hypothesis "ci" profile, fixes sys.path
    ├── fixtures/             # non-leaf fixture files (see fixtures/README.md)
    ├── test_*.py             # property tests (Hypothesis) + unit/example tests + static checks
    └── INTEGRATION_MANUAL.md # human-run, live-service test cases (not part of pytest)
```

Property tests use Hypothesis with a floor of **100 examples per test**,
enforced by the `"ci"` profile registered in `tests/conftest.py` (loaded
automatically on import — no `--hypothesis-profile` flag needed). Each
property test's docstring/comment references the design property it
validates, e.g. `Feature: terragrunt-pr-merge-workflow, Property 1: ...`.

Test files map to design/requirement areas:

| File | Covers |
|------|--------|
| `test_filter_leaves.py`, `test_exclusion_invariant.py` | Filter correctness, root/deep-path exclusion (Properties 1–2) |
| `test_parse_leaf.py`, `test_parse_leaf_no_env_validation.py` | Path_Parser (Property 3), no env-name validation (Req 4.3) |
| `test_matrix_entry_completeness.py`, `test_matrix_count_empty.py`, `test_matrix_cap.py` | Entry completeness, count/empty behavior, 256 cap (Properties 4–6) |
| `test_classify_source.py` | Source_Scheme classifier (Property 7) |
| `test_cli.py` | `main()` end-to-end via stdin/stdout injection |
| `test_detect_integration.py` | Offline integration: builds a throwaway git repo + merge commit, runs the real first-parent `git diff`, pipes into `detect_leaves.py` |
| `test_guard_merged_state.py`, `test_validate_entry.py`, `test_validate_secrets_vars.py`, `test_configure_module_auth.py`, `test_init_apply_gate.py`, `test_plan_dryrun_guard.py` | Subprocess-driven tests of the corresponding `.sh` helper (stubbed `git`/`terragrunt`/`ssh-keyscan` where needed) |
| `test_workflow_static.py` | Static source inspection of the workflow YAML + all `*.sh` helpers: apply-flag presence (Req 10.4), no raw secret ever echoed to stdout/stderr (Req 8.6/9.7) |
| `test_harness.py` | Sanity check on the test harness itself |

### 3.2 Set up a virtual environment

Run from `.github/scripts/`:

```bash
cd .github/scripts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

`.venv/`, `.pytest_cache/`, `.hypothesis/`, and `__pycache__/` under this
directory are already git-ignored (see the repo [`.gitignore`](../../.gitignore)).

### 3.3 Run the tests

Full suite:

```bash
cd .github/scripts
python3 -m pytest
```

Just the pure-logic property/unit tests for `detect_leaves.py`:

```bash
python3 -m pytest tests/test_filter_leaves.py tests/test_parse_leaf.py \
  tests/test_matrix_cap.py tests/test_matrix_count_empty.py \
  tests/test_matrix_entry_completeness.py tests/test_classify_source.py \
  tests/test_cli.py -v
```

The offline `git diff` + `detect_leaves.py` integration test (no network,
no credentials — safe to run anywhere):

```bash
python3 -m pytest tests/test_detect_integration.py -v
```

Bash-helper tests only (these shell out to the real script under test,
stubbing external binaries like `git`/`terragrunt` as needed — no live
GitHub/AWS access required):

```bash
python3 -m pytest tests/test_guard_merged_state.py tests/test_validate_entry.py \
  tests/test_validate_secrets_vars.py tests/test_configure_module_auth.py \
  tests/test_init_apply_gate.py -v
```

Static workflow/secret-hygiene checks:

```bash
python3 -m pytest tests/test_workflow_static.py -v
```

Useful flags:

```bash
# Re-run only what failed last time
python3 -m pytest --lf

# Bump Hypothesis examples for a deeper local run (CI floor is 100)
python3 -m pytest --hypothesis-seed=random -p hypothesis \
  -o hypothesis-profile=ci
```

### 3.4 actionlint (workflow YAML, not Python)

The Python suite above never parses the workflow YAML itself beyond the
static string checks in `test_workflow_static.py`. Structural validation of
`provision-on-merge.yml` (trigger, `if` gates, `environment: dev`, matrix
wiring) is `actionlint`'s job, run automatically by
[`lint-actions.yml`](../workflows/lint-actions.yml) on every push/PR that
touches `.github/workflows/**`. To run it locally:

```bash
curl -sSLo actionlint.tar.gz \
  https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_linux_amd64.tar.gz
tar -xzf actionlint.tar.gz actionlint
./actionlint -color
```

### 3.5 What's *not* covered by `pytest`

Anything that needs live GitHub Actions, real AWS credentials, a real S3
state bucket, or actual network access to the private modules repo is
**manual**, documented in
[`tests/INTEGRATION_MANUAL.md`](tests/INTEGRATION_MANUAL.md) — e.g. a real
merged PR reaching `terragrunt apply`, a failing leg alongside a passing one
under `fail-fast: false`, or an auth-rejection case with a deliberately bad
credential. Before promoting any such case to a real `apply`, prove the
non-mutating path first with
[`terragrunt_plan_dryrun.sh`](terragrunt_plan_dryrun.sh) (§1, "Not wired
into the workflow").
