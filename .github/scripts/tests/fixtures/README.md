# Integration / smoke fixtures

Fixtures and harnesses for the `terragrunt-pr-merge-workflow` feature's
integration / smoke layer (tasks.md task 13.1).

> **Important:** These fixtures live under `.github/scripts/tests/fixtures/`
> **on purpose**. Real leaf units live at `<TENANT>/<env>/terragrunt.hcl` at
> the repository root and are what the provision workflow's first-parent
> `git diff` + `detect_leaves.py` filter picks up. Anything placed here is
> several segments deep (`.github/scripts/tests/...`), so the anchored leaf
> regex `^[A-Za-z0-9]+/[A-Za-z0-9]+/terragrunt\.hcl$` never matches it. Do
> **not** move these fixtures to the repo root, where they would be treated as
> real tenants.

## Contents

- `leaves/https_source/terragrunt.hcl` — fixture leaf with an HTTPS `git::`
  module source (exercises the HTTPS auth path, Req 9.2).
- `leaves/ssh_source/terragrunt.hcl` — fixture leaf with an SSH `git::` module
  source (exercises the SSH auth path, Req 9.3).
- `root.hcl` — a standalone root config used only by the terragrunt plan
  dry-run harness so a fixture leaf can `include` a parent root without
  depending on the repo-root `root.hcl`.
- `../test_detect_integration.py` — an **offline** pytest that builds a
  throwaway git repo containing a merge commit, runs the first-parent
  `git diff --name-only --diff-filter=AM <merge>^1 <merge>` path, pipes the
  result into `detect_leaves.py`, and asserts the expected matrix
  (Req 3.1, 3.3). Runs with no network or credentials.
- `../../terragrunt_plan_dryrun.sh` — an **optional / manual** harness that runs
  `terragrunt init` + `terragrunt plan` against a fixture leaf to confirm
  backend resolution, module auth, and working-directory selection **without**
  applying (Req 9.2, 9.3, 10.1). It is gated: it self-skips (exit 0 with a
  SKIP notice) when `terragrunt` or the required live credentials
  (`TG_STATE_BUCKET`, `AWS_REGION`, AWS creds, and module-auth secrets) are
  unavailable, because it needs network and private-module access.

## Running the offline harness

```bash
cd .github/scripts
python3 -m pytest tests/test_detect_integration.py -v
```

## Running the terragrunt plan dry-run (manual)

Requires `terragrunt`, network access to the private modules repo, AWS
credentials, and a real (or test) S3 state bucket. This performs **no** apply.

```bash
export TG_STATE_BUCKET=<test-bucket>
export AWS_REGION=ap-southeast-2
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
# For the HTTPS fixture:
export TOKEN=<github-token>
# or, for the SSH fixture:
export SECURITY_KEY="$(cat ~/.ssh/id_ed25519)"

.github/scripts/terragrunt_plan_dryrun.sh https   # or: ssh
```
