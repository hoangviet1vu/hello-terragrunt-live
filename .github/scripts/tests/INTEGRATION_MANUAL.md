# Manual / optional integration tests

Manual, live-service integration cases for the `terragrunt-pr-merge-workflow`
feature (tasks.md **task 13.2**).

These cases exercise external services — GitHub Actions, GitHub's merge/diff
behavior, git auth against the private modules repo, AWS S3 remote state, and
Terragrunt itself — so they **cannot** run as offline unit tests. They are run
**manually**, by a human, against a throwaway tenant/env and a **test** S3 state
bucket. Each case uses **1–3 examples**, not property generators, because the
external behavior is deterministic with respect to our inputs and costly to
repeat.

> The offline logic core (path filter, parser, matrix builder, source-scheme
> classifier) and the step-logic helpers are already covered by the pytest /
> Hypothesis suite under `.github/scripts/tests/`. This document covers only the
> live end-to-end behavior that the automated suite cannot.

## Relationship to the automated harnesses

Two existing harnesses back these manual cases; **do not re-implement them** —
reference them:

- **Offline detect integration** — `tests/test_detect_integration.py` builds a
  throwaway git repo with a merge commit, runs the first-parent
  `git diff --name-only --diff-filter=AM <merge>^1 <merge>` path, pipes it into
  `detect_leaves.py`, and asserts the matrix (Req 3.1, 3.3). Run it first; it
  needs no network or credentials:

  ```bash
  cd .github/scripts
  python3 -m pytest tests/test_detect_integration.py -v
  ```

- **Terragrunt plan dry-run** — `.github/scripts/terragrunt_plan_dryrun.sh`
  runs `terragrunt init` + `terragrunt plan` (never `apply`) against a fixture
  leaf to confirm backend resolution, module auth, and working-directory
  selection **without mutating infrastructure** (Req 9.2, 9.3, 10.1).

## Plan-first rule (prove plan before promoting to apply)

Every case below that ends in a real `terragrunt apply` MUST first be proven on
the **plan** path. The workflow provisions with `apply`, but you validate the
same backend + auth + working-directory wiring non-destructively with the
dry-run harness before letting any live run reach `apply`:

```bash
export TG_STATE_BUCKET=<test-bucket>
export AWS_REGION=ap-southeast-2
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
# HTTPS fixture:
export TOKEN=<github-token>
# or SSH fixture:
export SECURITY_KEY="$(cat ~/.ssh/id_ed25519)"

# Non-mutating: init + plan only, no apply.
.github/scripts/terragrunt_plan_dryrun.sh https   # or: ssh
```

Only after the dry-run reports `PASS` for the scheme you intend to use should
you promote a case to a real merge that triggers `apply`.

## Shared preconditions

Unless a case says otherwise, all cases assume:

- A `dev` GitHub Environment configured on the repo with:
  - **secrets** `TOKEN`, `SECURITY_KEY`, `AWS_ACCESS_KEY_ID`,
    `AWS_SECRET_ACCESS_KEY`
  - **variables** `AWS_REGION`, `TG_STATE_BUCKET` (pointing at a **test**
    bucket, not production)
- The `provision-on-merge` workflow present on `main`
  (`.github/workflows/provision-on-merge.yml`).
- Write access to open PRs against `main` and to observe Actions runs.
- A throwaway tenant you are willing to create/destroy, e.g. `ITTEST` (uppercase
  tenant ID per repo convention), with a `dev` env leaf. Clean up any created
  AWS resources and the test state object afterward.

Each case lists: **Requirements**, **Preconditions**, **Steps** (how to craft
the PR / merge state), and **Expected observable outcome**.

---

## Case 1 — `merged=false` → no provision

**Requirements:** 1.1, 1.2

**Preconditions:** Shared preconditions. No throwaway leaf changes required.

**Steps:**
1. Open a PR against `main` (any content is fine; a trivial README edit works).
2. **Close the PR without merging it** (use "Close pull request", not "Merge").

**Expected observable outcome:**
- The `pull_request` `closed` event dispatches a workflow run within ~60s
  (Req 1.1).
- The `detect` job's `if: github.event.pull_request.merged == true` gate is
  false, so `detect` is skipped and `provision` never runs.
- The overall run concludes **successfully** with **zero** provision jobs — no
  Terragrunt is invoked and no state is touched (Req 1.2).

---

## Case 2 — only-`root.hcl` PR → empty matrix, zero provision jobs

**Requirements:** 2.4

**Preconditions:** Shared preconditions.

**Steps:**
1. Create a branch and modify **only** the repo-root `root.hcl` (e.g. add a
   comment line). Do not touch any `<tenant>/<env>/terragrunt.hcl`.
2. Open a PR against `main` and **merge** it.

**Expected observable outcome:**
- `detect` runs (PR was merged). The first-parent diff yields only `root.hcl`,
  which the anchored leaf filter excludes, so `detect_leaves.py` emits
  `matrix=[]` and `has_units=false`.
- The `provision` job is **skipped** by
  `if: needs.detect.outputs.has_units == 'true'`.
- The overall run concludes **successfully** with **zero** provision jobs
  (Req 2.4).

---

## Case 3 — valid leaf PR → single provision leg reaches init/apply

**Requirements:** 3.1, 3.3

**Preconditions:**
- Shared preconditions.
- **Plan-first proven:** run `terragrunt_plan_dryrun.sh` for the scheme your
  throwaway leaf uses and confirm it reports `PASS` before doing this case.

**Steps:**
1. On a branch, add a single valid leaf unit at `ITTEST/dev/terragrunt.hcl`
   (copy the shape of `SAMPLETENANT/dev/terragrunt.hcl`; set `tenant_name` to
   `ITTEST`). Use a source scheme whose auth secret is configured in `dev`.
2. Open a PR against `main` and **merge** it.

**Expected observable outcome:**
- `detect` compares the merge commit against its first parent
  (`git diff --diff-filter=AM <merge>^1 <merge>`) and finds exactly one added
  leaf, `ITTEST/dev/terragrunt.hcl` (Req 3.1). Deleted/renamed-away files, had
  there been any, are excluded (Req 3.3).
- `provision` fans out to **exactly one** leg for `ITTEST/dev`, bound to `dev`,
  which reaches `terragrunt init` then `terragrunt apply` in `ITTEST/dev`.
- The leg succeeds and the overall run concludes successfully.
- **Cleanup:** destroy the `ITTEST/dev` resources and remove its
  `s3://<TG_STATE_BUCKET>/ITTEST/dev/terraform.tfstate` object.

---

## Case 4 — failing leg alongside passing leg → both complete, run fails

**Requirements:** 5.7, 5.8, 11.3, 11.4

**Preconditions:**
- Shared preconditions.
- **Plan-first proven** for the passing leg's scheme.

**Steps:**
1. On a branch, add **two** valid leaf units in the same PR:
   - `ITTEST/dev/terragrunt.hcl` — a valid, appliable leaf (the **passing**
     leg).
   - `ITTEST/broken/terragrunt.hcl` — a leaf crafted to **fail** at
     init/apply. A reliable way is to point its module `source` `?ref=` at a
     non-existent tag, or set an input that the module rejects, so the leg
     fails deterministically without depending on credentials.
2. Open a PR against `main` and **merge** it.

**Expected observable outcome:**
- `detect` emits a matrix with **two** entries; `provision` fans out two legs
  under `strategy.fail-fast: false`.
- The `ITTEST/broken` leg fails, but because `fail-fast: false`, the
  `ITTEST/dev` leg is **not** cancelled and **runs to completion** (Req 5.7,
  11.3).
- After all legs finish, GitHub aggregates the results: at least one leg failed,
  so the `provision` job and the **overall run report failed** (Req 5.8, 11.4).
- **Cleanup:** destroy any resources the passing leg created and remove its
  state object.

---

## Case 5 — bad-credential fixture → auth-rejection failure

**Requirements:** 9.6

**Preconditions:**
- Shared preconditions, **except** deliberately supply an **invalid** module-auth
  secret in the `dev` environment for the scheme under test:
  - HTTPS scheme: set `TOKEN` to a revoked/garbage token.
  - SSH scheme: set `SECURITY_KEY` to a private key not authorized on the
    modules repo.
- Note the secret is present but **wrong** — this tests auth *rejection during
  fetch* (Req 9.6), not the *missing-secret* guards (Req 9.4/9.5, which are
  covered offline in `tests/test_configure_module_auth.py`).

**Steps:**
1. Confirm the invalid secret is set in the `dev` environment for the scheme you
   will use.
2. On a branch, add a valid leaf `ITTEST/dev/terragrunt.hcl` that references the
   modules repo over the chosen scheme.
3. Open a PR against `main` and **merge** it.

**Expected observable outcome:**
- The `Configure module auth` step succeeds (the secret is present, just wrong),
  so no missing-secret guard trips.
- `terragrunt init` attempts to fetch the private modules repo and git
  **rejects** authentication; the fetch fails and `init` exits non-zero.
- The provision leg fails via the init failure path with an
  authentication-failure indication, and the overall run reports failed
  (Req 9.6). No `apply` runs.
- The raw secret value never appears in logs (GitHub masking + the helper never
  echoes it).
- **Cleanup:** restore the correct `dev` secret afterward.

---

## Requirement → case coverage

| Requirement | Case |
|-------------|------|
| 1.1 (run starts on PR closed) | Case 1 |
| 1.2 (merged=false → no provision, run succeeds) | Case 1 |
| 2.4 (only excluded files → empty matrix, zero jobs) | Case 2 |
| 3.1 (first-parent diff finds the leaf) | Case 3 |
| 3.3 (deleted/renamed-away excluded) | Case 3 |
| 5.7 (one leg fails, others keep running) | Case 4 |
| 5.8 (any failure → overall failed) | Case 4 |
| 9.6 (auth rejected on fetch → auth-failure) | Case 5 |
| 11.3 (one leg fails, others complete) | Case 4 |
| 11.4 (any failure after all complete → overall failed) | Case 4 |

## Cleanup checklist

After any case that reached a real `apply`:

- Destroy the throwaway tenant/env resources (`terragrunt destroy` in the leaf
  dir, or tear down via the console).
- Delete the leaf's state object under
  `s3://<TG_STATE_BUCKET>/<TENANT>/<env>/terraform.tfstate`.
- Remove the throwaway leaf directories from `main` (revert PR) so they are not
  picked up by future runs.
- Restore any secret/variable you deliberately corrupted for Case 5.
