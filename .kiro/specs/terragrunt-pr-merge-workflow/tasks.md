# Implementation Plan: terragrunt-pr-merge-workflow

## Overview

This plan implements the PR-merge provisioning workflow in two layers, per the design:

1. **Pure-logic core** — a small, self-contained script that reads a newline-delimited list
   of changed paths on stdin and emits a JSON matrix plus `has_units` on stdout. It holds all
   the input-varying behavior: the anchored path filter, the Path_Parser (tenant + workDir),
   the matrix builder (256 cap + empty-set handling), and the Source_Scheme classifier. This
   layer carries all seven Correctness Properties and is property/unit tested off the runner.
2. **Declarative GitHub Actions workflow YAML** — wires `detect` -> matrix -> `provision`,
   including the merged-state gate, first-parent `git diff`, per-leg validation/auth/init-apply
   steps, and error reporting. Validated with `actionlint`, static grep checks, and a small
   set of integration/smoke runs.

**Implementation language for the logic core: Python 3**, using **Hypothesis** for
property-based tests and **pytest** for unit/example tests. (The design permits Python w/
Hypothesis or Node w/ fast-check; Python + Hypothesis is selected here.) The logic core is a
Python module invoked by a thin shell wrapper in the workflow.

Tasks build incrementally: scaffold -> filter -> parser -> matrix builder -> classifier ->
CLI wiring (each with its property tests placed next to the implementation), then the step
logic unit tests, then the workflow YAML, then static validation, then integration/smoke.

## Tasks

- [x] 1. Scaffold the logic-core project and test harness
  - Create `.github/scripts/` for the runtime script and `.github/scripts/tests/` for tests
  - Create the Python package/module file `.github/scripts/detect_leaves.py` with placeholder
    pure functions: `filter_leaves(paths) -> list[str]`, `parse_leaf(path) -> dict`,
    `build_matrix(paths) -> (list[dict], bool)`, `classify_source(source) -> str`
  - Add `.github/scripts/requirements-dev.txt` pinning `hypothesis` and `pytest`
  - Add `pytest` configuration (e.g. `pytest.ini` or `pyproject.toml`) and a Hypothesis
    profile setting a minimum of 100 examples per property test
  - _Requirements: 3.2, 4.1, 4.2, 5.1, 9.1_

- [x] 2. Implement the path filter (anchored leaf regex)
  - [x] 2.1 Implement `filter_leaves` in `detect_leaves.py`
    - Compile the anchored pattern `^[A-Za-z0-9]+/[A-Za-z0-9]+/terragrunt\.hcl$`
    - Return exactly the input paths matching it, preserving order and de-duplicating
    - Ensure `root.hcl` at any depth, repo-root `terragrunt.hcl`, and deep paths
      (`a/b/c/terragrunt.hcl`) never match
    - _Requirements: 2.1, 2.2, 2.3, 3.2_

  - [x] 2.2 Write property test for filter correctness
    - **Property 1: Filter correctness (matched set equals leaf-regex set)**
    - Tag: `Feature: terragrunt-pr-merge-workflow, Property 1: filter correctness`
    - Generator mixes valid leaves, near-miss roots (`root.hcl` at various depths, top-level
      `terragrunt.hcl`), deep paths, and malformed paths; assert output == inputs satisfying
      the regex (no false positives, no false negatives); min 100 iterations
    - _Requirements: 2.1, 3.2_

  - [x] 2.3 Write property test for the exclusion invariant
    - **Property 2: Exclusion invariant (root config never included)**
    - Tag: `Feature: terragrunt-pr-merge-workflow, Property 2: exclusion invariant`
    - For any input list, assert no kept path has basename `root.hcl`, no kept path is a
      single-segment `terragrunt.hcl`, and no kept path has fewer than two dir segments before
      the filename; min 100 iterations
    - _Requirements: 2.2, 2.3, 4.4_

- [x] 3. Implement the Path_Parser (tenant + workDir)
  - [x] 3.1 Implement `parse_leaf` in `detect_leaves.py`
    - Split on `/`; set `tenant` = first segment, `envDir` = second segment,
      `workDir` = `<tenant>/<envDir>` (leaf path with `/terragrunt.hcl` removed),
      `leafPath` = the input path
    - Do NOT derive or validate any environment name beyond carrying `envDir` for reporting
    - Raise/flag a malformed error for a path with fewer than two segments before the filename
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 3.2 Write property test for parse correctness
    - **Property 3: Parse correctness (tenant and workDir derivation)**
    - Tag: `Feature: terragrunt-pr-merge-workflow, Property 3: parse correctness`
    - For any matched leaf path, assert `entry.tenant == firstSegment`,
      `entry.workDir == parentDirectory`, and `entry.workDir == tenant + "/" + envDir`;
      min 100 iterations
    - _Requirements: 4.1, 4.2_

  - [x] 3.3 Write example test asserting no env validation branch
    - Confirm `parse_leaf` accepts arbitrary `envDir` values without rejecting/validating them
    - _Requirements: 4.3_

- [x] 4. Implement the matrix builder (cap + empty-set handling)
  - [x] 4.1 Implement `build_matrix` in `detect_leaves.py`
    - Compose `filter_leaves` then `parse_leaf` to produce a list of matrix entry dicts
      (`tenant`, `envDir`, `workDir`, `leafPath`)
    - Return `([], False)` for zero matches; `(entries, True)` for 1..256 matches
    - Signal an error (raise / non-zero) with a "maximum matrix size exceeded" message when
      matches exceed 256, emitting no matrix
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 4.2 Write property test for entry completeness
    - **Property 4: Entry completeness**
    - Tag: `Feature: terragrunt-pr-merge-workflow, Property 4: entry completeness`
    - For any input list, assert every emitted entry has non-empty `tenant`, `workDir`, and
      `leafPath`; min 100 iterations
    - _Requirements: 5.5, 5.6_

  - [x] 4.3 Write property test for count and empty behavior
    - **Property 5: Count and empty behavior**
    - Tag: `Feature: terragrunt-pr-merge-workflow, Property 5: count and empty behavior`
    - For inputs yielding N matches with 0 <= N <= 256, assert matrix length == N, and N == 0
      yields the empty array; min 100 iterations
    - _Requirements: 2.4, 3.4, 5.1, 5.2, 5.4_

  - [x] 4.4 Write property test for matrix cap enforcement
    - **Property 6: Matrix cap enforcement**
    - Tag: `Feature: terragrunt-pr-merge-workflow, Property 6: matrix cap enforcement`
    - Generate lists sized around the boundary (255, 256, 257); assert >256 matches signals an
      error and emits no matrix, and 256 succeeds; min 100 iterations
    - _Requirements: 5.3_

- [x] 5. Implement the Source_Scheme classifier
  - [x] 5.1 Implement `classify_source` in `detect_leaves.py`
    - Return `"https"` for a source beginning with `git::https://`, `"ssh"` for one beginning
      with `git::git@` or `git::ssh://`, otherwise `"unrecognized"`
    - Classify on the transport prefix only, ignoring repository, path, and `?ref=` portions
    - _Requirements: 9.1_

  - [x] 5.2 Write property test for source scheme classification
    - **Property 7: Source scheme classification**
    - Tag: `Feature: terragrunt-pr-merge-workflow, Property 7: source scheme classification`
    - Generate `git::` source strings (varying repo/path/ref) plus non-git strings; assert the
      classification depends only on the prefix; min 100 iterations
    - _Requirements: 9.1_

- [x] 6. Wire the pure functions into the stdin/stdout CLI
  - [x] 6.1 Add a `main()` entry point to `detect_leaves.py`
    - Read newline-delimited changed paths from stdin, call `build_matrix`
    - Write the JSON matrix and `has_units` to stdout in the `detect`-job output format
      (GITHUB_OUTPUT-compatible), and exit non-zero with a clear message on cap-exceeded
    - Emit `matrix=[]` and `has_units=false` on empty input
    - _Requirements: 2.5, 3.4, 5.3, 5.4, 5.5_

  - [x] 6.2 Write unit tests for the CLI end-to-end (stdin -> stdout)
    - Feed sample path lists (empty, single leaf, multiple leaves, only-root, >256) and assert
      the emitted `matrix`/`has_units` and exit codes
    - _Requirements: 2.4, 2.5, 3.4, 5.1, 5.2, 5.3, 5.4_

- [x] 7. Checkpoint - logic core complete and tested
  - Ensure all property and unit tests pass, ask the user if questions arise.

- [x] 8. Implement and unit-test the provision-step logic helpers
  - [x] 8.1 Implement a merged-state guard helper
    - A small script/function that accepts the `merged` value and exits non-zero with
      "merged state indeterminable" for anything other than `true`/`false`
    - _Requirements: 1.3, 1.5_

  - [x] 8.2 Write unit tests for the merged-state guard
    - Cases: `merged` in `{"", "null", "yes"}` fail; `true`/`false` behave as specified
    - _Requirements: 1.5_

  - [x] 8.3 Implement a validate-entry helper
    - Fail early with an identifying message if `tenant`, `workDir`, or `leafPath` is empty;
      also flag a path malformed (fewer than two leading segments)
    - _Requirements: 4.4, 5.6_

  - [x] 8.4 Write unit tests for validate-entry
    - Blank each field in turn; assert failure names the missing field before provisioning
    - _Requirements: 5.6_

  - [x] 8.5 Implement a validate-secrets/vars helper
    - Confirm `TG_STATE_BUCKET`, `AWS_REGION` (variables) and `AWS_ACCESS_KEY_ID`,
      `AWS_SECRET_ACCESS_KEY` (secrets) are present and non-empty; fail before any Terragrunt
      invocation with a message naming the missing value; validate `TOKEN`/`SECURITY_KEY`
      conditionally by scheme (in the auth helper), not unconditionally
    - _Requirements: 6.3, 6.4, 7.3, 7.4, 7.5, 8.4, 8.5_

  - [x] 8.6 Write unit tests for validate-secrets/vars ordering
    - Blank each var/secret in turn; assert failure occurs before any Terragrunt call and no
      remote-state access happens
    - _Requirements: 6.4, 7.3, 7.4, 7.5, 8.4, 8.5_

  - [x] 8.7 Implement the module-auth-by-scheme helper
    - Read the leaf `source`, call `classify_source`; for HTTPS require `TOKEN` and configure a
      credential URL rewrite; for SSH require `SECURITY_KEY` and install it as a `600`-mode key
      with a `github.com` known_hosts entry; fail before init on missing secret or unrecognized
      scheme, making no git/SSH config change on failure; never echo secret values
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.7_

  - [x] 8.8 Write unit tests for the auth handler
    - Cases: https-with-TOKEN, ssh-with-SECURITY_KEY, https-missing-TOKEN,
      ssh-missing-SECURITY_KEY, unrecognized scheme; assert no config change and correct error
      on failure paths
    - _Requirements: 9.2, 9.3, 9.4, 9.5_

  - [x] 8.9 Implement the init->apply gate helper
    - Run `terragrunt init` (non-interactive); run `terragrunt apply -auto-approve -input=false`
      only if init exit code is zero; on init failure skip apply and report failure with the
      `<tenant>/<env>` path; on apply failure report failure with the `<tenant>/<env>` path
    - _Requirements: 10.2, 10.3, 10.4, 10.5, 10.6, 11.1, 11.2_

  - [x] 8.10 Write unit tests for the init->apply gate
    - Simulate init/apply exit codes (init=1 skips apply and fails; init=0/apply=0 succeeds;
      init=0/apply=1 fails); assert error messages contain `<tenant>/<env>`
    - _Requirements: 10.2, 10.3, 10.5, 10.6, 11.1, 11.2_

- [x] 9. Checkpoint - step logic helpers complete and tested
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Author the GitHub Actions workflow YAML (trigger + detect job)
  - [x] 10.1 Create the workflow file with trigger and merged-state gate
    - Create `.github/workflows/provision-on-merge.yml` with
      `on.pull_request: { types: [closed], branches: [main] }` and least-privilege
      `permissions: { contents: read }`
    - Add the `detect` job with `if: github.event.pull_request.merged == true` and an explicit
      guard step (via the helper) that fails on an indeterminable merged state before detection
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 10.2 Implement the detect job change detection and matrix output
    - `actions/checkout` with `fetch-depth: 0`; run
      `git diff --name-only --diff-filter=AM "$MERGE_SHA^1" "$MERGE_SHA"` using
      `github.event.pull_request.merge_commit_sha`, piping the result into `detect_leaves.py`
    - Fail the job with "change detection could not be completed" when the parent diff cannot be
      performed; expose `matrix` and `has_units` as job outputs
    - _Requirements: 2.1, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 5.3, 5.4, 5.5_

- [x] 11. Author the provision matrix job in the workflow YAML
  - [x] 11.1 Define the provision job matrix, gating, and environment binding
    - `needs: detect`, `if: needs.detect.outputs.has_units == 'true'`,
      `environment: dev`, `strategy.fail-fast: false`, and
      `matrix.include: ${{ fromJSON(needs.detect.outputs.matrix) }}`
    - _Requirements: 2.4, 3.4, 5.1, 5.2, 5.4, 5.7, 5.8, 6.1, 6.2, 11.3, 11.4, 11.5_

  - [x] 11.2 Add validate-entry and validate-secrets/vars steps
    - Wire the validate-entry helper (8.3) and validate-secrets/vars helper (8.5) as the first
      steps, reading secrets/vars from the `dev` environment and failing before any Terragrunt
      or state access
    - _Requirements: 5.6, 6.3, 6.4, 7.3, 7.4, 7.5, 8.4, 8.5_

  - [x] 11.3 Add setup and environment-export steps
    - Pin `hashicorp/setup-terraform` (fixed Terraform version) and install a pinned Terragrunt
      version; export `TG_STATE_BUCKET`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`,
      `AWS_SECRET_ACCESS_KEY` into the job env for `root.hcl`'s `get_env` and the AWS session
    - _Requirements: 7.1, 7.2, 8.1, 8.2, 8.3_

  - [x] 11.4 Add the configure-module-auth-by-scheme step
    - Wire the auth helper (8.7), passing `TOKEN`/`SECURITY_KEY` via `env:` only; run before init
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 11.5 Add the terragrunt init + apply step with per-job error reporting
    - Set `working-directory: ${{ matrix.workDir }}`; wire the init->apply gate (8.9) running
      init then, only on success, `apply -auto-approve -input=false --terragrunt-non-interactive`;
      emit `::error::` annotations naming `<tenant>/<env>` on init/apply failure
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.1, 11.2_

- [x] 12. Add workflow static validation (actionlint + grep checks)
  - [x] 12.1 Add an actionlint validation workflow/step
    - Create `.github/workflows/lint-actions.yml` (or a job) that runs `actionlint` against the
      workflow files to validate YAML/expressions/contexts, the trigger, `if` gates,
      `environment: dev`, matrix wiring, and `fail-fast: false`
    - _Requirements: 1.2, 1.3, 1.4, 5.7, 6.1, 6.2, 6.3, 10.4, 11.3, 11.4, 11.5_

  - [x] 12.2 Add static grep checks for apply flags and secret hygiene
    - Assert `-auto-approve` and `-input=false` are present in the workflow, and that no
      `echo`/`cat` of secret env vars (`TOKEN`, `SECURITY_KEY`, `AWS_*`) exists
    - _Requirements: 8.6, 9.7, 10.4_

- [x] 13. Add integration/smoke validation fixtures and harness
  - [x] 13.1 Create fixtures and a plan/dry-run harness for detect + auth + workdir
    - Add fixture leaf units (one SSH-source, one HTTPS-source) and a small script/test-repo
      setup exercising the first-parent `git diff` path and `detect_leaves.py` end-to-end
    - Provide a `terragrunt plan` (init + plan) dry-run path against a fixture leaf to confirm
      backend resolution, module auth, and working-directory selection without mutating infra
    - _Requirements: 3.1, 3.3, 9.2, 9.3, 10.1_

  - [x] 13.2 Add integration cases requiring live GitHub/AWS (manual/optional)
    - Representative runs (each 1-3 examples), promoted from plan to apply once the plan path is
      proven: `merged=false` -> no provision; only-`root.hcl` PR -> empty matrix; valid leaf PR
      -> single leg reaches init/apply; failing-leg-alongside-passing-leg -> both complete and
      run fails; bad-credential fixture -> auth-rejection failure. These require live
      GitHub/AWS and are run manually, not as unit tests.
    - _Requirements: 1.1, 1.2, 2.4, 3.1, 3.3, 5.7, 5.8, 9.6, 11.3, 11.4_

- [x] 14. Final checkpoint - all automated tests and static checks pass
  - Ensure all property, unit, and static-validation checks pass, ask the user if questions
    arise.

## Notes

- Tasks marked with `*` are optional (all are test or static-check sub-tasks) and can be
  skipped for a faster MVP; core implementation tasks are never optional.
- The implementation language for the logic core is **Python 3** with **Hypothesis** (PBT) and
  **pytest** (unit/example). All property tests run a minimum of 100 iterations and are tagged
  `Feature: terragrunt-pr-merge-workflow, Property N: ...`.
- Property tests are placed next to the implementation they validate so edge cases are caught
  early (Properties 1-7 across tasks 2-5).
- Each task references the specific requirement numbers and/or design properties it implements
  for traceability.
- Integration/smoke steps that require live GitHub/AWS are marked optional/manual because they
  exercise external services and cannot be run in unit form.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "5.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "3.1", "5.2"] },
    { "id": 3, "tasks": ["3.2", "3.3", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4", "6.1"] },
    { "id": 5, "tasks": ["6.2", "8.1", "8.3", "8.5", "8.7", "8.9"] },
    { "id": 6, "tasks": ["8.2", "8.4", "8.6", "8.8", "8.10", "10.1"] },
    { "id": 7, "tasks": ["10.2"] },
    { "id": 8, "tasks": ["11.1"] },
    { "id": 9, "tasks": ["11.2", "11.3", "11.4", "11.5"] },
    { "id": 10, "tasks": ["12.1", "13.1"] },
    { "id": 11, "tasks": ["12.2", "13.2"] }
  ]
}
```
