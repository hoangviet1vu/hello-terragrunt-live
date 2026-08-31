# Requirements Document

## Introduction

This feature adds a GitHub Actions workflow to the `hello-terragrunt-live` repository that automatically provisions tenant platforms when a pull request is merged into the `main` branch. The workflow detects which leaf Terragrunt units (`<tenant>/<env>/terragrunt.hcl`) were created or updated by the merged pull request, fans out one job per changed leaf unit, binds each job to the `dev` GitHub Environment to select environment-scoped secrets and variables, authenticates to the private modules repository, and runs Terragrunt to apply the change. The root configuration (`root.hcl` and any top-level `terragrunt.hcl`) is explicitly excluded from triggering the workflow.

## Glossary

- **Workflow**: The GitHub Actions workflow defined in the repository that provisions tenant platforms on pull request merge into `main`.
- **Change_Detector**: The Workflow component responsible for determining which leaf Terragrunt units were added or modified by the merged pull request.
- **Path_Parser**: The Workflow component that extracts the tenant identifier and the leaf unit directory path from a leaf unit file path.
- **Provision_Job**: A GitHub Actions job that runs Terragrunt against a single leaf Terragrunt unit.
- **Leaf_Unit**: A Terragrunt configuration file located at `<tenant>/<env>/terragrunt.hcl`, where `<tenant>` is a tenant identifier of any case (letters A-Z or a-z and digits) and `<env>` is an environment folder name.
- **Root_Config**: The shared Terragrunt configuration file `root.hcl` at the repository root and any top-level `terragrunt.hcl`, which the Workflow MUST NOT treat as a Leaf_Unit.
- **GitHub_Environment**: The GitHub Actions Environment named `dev` that scopes the secrets and variables used by every Provision_Job.
- **Modules_Repository**: The private Git repository `hoangviet1vu/hello-terragrunt-modules` that supplies Terraform modules referenced by each Leaf_Unit, referenced via either an HTTPS source scheme (`git::https://...`) or an SSH source scheme (`git::git@...`).
- **Source_Scheme**: The Git transport scheme declared in a Leaf_Unit's Terragrunt `source`, either the HTTPS form (`git::https://...`) or the SSH form (`git::git@...`).
- **SECURITY_KEY**: The GitHub_Environment secret holding the SSH private key used to authenticate to the Modules_Repository when the Source_Scheme is the SSH form.
- **Merged_Pull_Request**: A pull request whose target branch is `main` and whose merged state is true.

## Requirements

### Requirement 1: Trigger on Pull Request Merge to Main

**User Story:** As a platform engineer, I want the Workflow to run only when a pull request is merged into `main`, so that tenant platforms are provisioned from reviewed and approved changes.

#### Acceptance Criteria

1. WHEN a pull request targeting the `main` branch is closed with a merged state of true, THE Workflow SHALL start execution within 60 seconds of receiving the pull request closed event.
2. IF a pull request targeting the `main` branch is closed with a merged state of false, THEN THE Workflow SHALL NOT execute the Provision_Job stage and SHALL terminate with a completed status indicating no provisioning was performed.
3. WHERE the Workflow is triggered by a pull request closed event, THE Workflow SHALL evaluate the merged state before performing change detection.
4. IF a pull request targeting a branch other than `main` is closed, THEN THE Workflow SHALL NOT start execution.
5. IF the merged state cannot be determined from the pull request closed event payload, THEN THE Workflow SHALL NOT execute the Provision_Job stage and SHALL terminate with a failed status and an error indication that the merged state was indeterminable.

### Requirement 2: Path Filtering for Leaf Units

**User Story:** As a platform engineer, I want the Workflow to react only to leaf Terragrunt units, so that shared root configuration changes do not trigger tenant provisioning.

#### Acceptance Criteria

1. WHEN the Merged_Pull_Request contains one or more changed files whose path matches `<tenant>/<env>/terragrunt.hcl`, where `<tenant>` and `<env>` are each one path segment of letters (A-Z or a-z) and digits, THE Workflow SHALL proceed with change detection.
2. WHEN the Workflow computes the set of files that trigger provisioning, THE Workflow SHALL exclude any file named `root.hcl` at any path depth.
3. WHEN the Workflow computes the set of files that trigger provisioning, THE Workflow SHALL exclude any `terragrunt.hcl` located at the repository root (path depth of exactly one segment, i.e. no parent directory).
4. IF the Merged_Pull_Request modifies only files that are excluded per criteria 2 and 3 and contains zero files matching the Leaf_Unit path pattern defined in criterion 1, THEN THE Workflow SHALL complete with a success status and SHALL execute zero Provision_Job instances.
5. IF the Merged_Pull_Request contains zero changed files matching the Leaf_Unit path pattern defined in criterion 1, THEN THE Workflow SHALL complete change detection within 60 seconds and SHALL produce an output indicating that no leaf units were detected.

### Requirement 3: Change Detection of Leaf Units

**User Story:** As a platform engineer, I want the Workflow to identify exactly which leaf units were added or modified, so that only affected tenant platforms are provisioned.

#### Acceptance Criteria

1. WHEN the Workflow starts, THE Change_Detector SHALL compute the set of files added or modified by the Merged_Pull_Request by comparing the merge commit against its first parent commit.
2. THE Change_Detector SHALL include in the change set only files whose path matches the pattern `<tenant>/<env>/terragrunt.hcl`, where `<tenant>` and `<env>` are each a single path segment of one or more letters (uppercase or lowercase) and digits, excluding the root `terragrunt.hcl`.
3. THE Change_Detector SHALL exclude from the change set all files whose change type is deleted or renamed-away, retaining only files with change type added or modified.
4. IF the computed change set contains zero matching files, THEN THE Workflow SHALL complete with a success status and SHALL NOT trigger any Provision_Job.
5. IF the comparison against the parent commit cannot be performed because the required commit history is unavailable, THEN THE Change_Detector SHALL fail the Workflow with a non-success status and SHALL emit an error message indicating that change detection could not be completed.

### Requirement 4: Parse Tenant and Directory from Path

**User Story:** As a platform engineer, I want the Workflow to derive the tenant and working directory from each leaf unit path, so that Terragrunt runs against the correct directory for the changed unit.

#### Acceptance Criteria

1. WHEN a Leaf_Unit is present in the change set, THE Path_Parser SHALL split the Leaf_Unit path on the `/` delimiter and extract the tenant identifier from the first path segment.
2. WHEN a Leaf_Unit is present in the change set, THE Path_Parser SHALL derive the working directory as the parent directory of the Leaf_Unit file.
3. THE Path_Parser SHALL NOT derive or validate any environment name from the Leaf_Unit path.
4. IF the Leaf_Unit path contains fewer than two path segments before the file name, THEN THE Path_Parser SHALL fail the corresponding Provision_Job with an error indication that the path is malformed.

### Requirement 5: Matrix Fan-Out per Changed Leaf Unit

**User Story:** As a platform engineer, I want each changed leaf unit provisioned in its own job, so that multiple tenant or environment changes in a single pull request run independently.

#### Acceptance Criteria

1. WHEN the change set contains exactly one Leaf_Unit, THE Workflow SHALL execute exactly one Provision_Job for that Leaf_Unit.
2. WHEN the change set contains between 2 and 256 Leaf_Units, THE Workflow SHALL execute one Provision_Job per Leaf_Unit using a matrix strategy over the change set.
3. IF the change set contains more than 256 Leaf_Units, THEN THE Workflow SHALL fail before executing any Provision_Job and produce an error indication reporting that the maximum matrix size was exceeded.
4. WHEN the change set contains zero Leaf_Units, THE Workflow SHALL complete without executing any Provision_Job.
5. THE Workflow SHALL provide each Provision_Job with the Leaf_Unit path, the parsed tenant identifier, and the derived working directory.
6. IF the Leaf_Unit path, parsed tenant identifier, or derived working directory is missing or empty for a Leaf_Unit, THEN THE Workflow SHALL fail that Leaf_Unit's Provision_Job before provisioning and produce an error indication identifying the missing value.
7. IF one Provision_Job fails, THEN THE Workflow SHALL continue executing all remaining Provision_Job runs to completion without cancelling them.
8. WHEN all Provision_Job runs have completed and at least one Provision_Job has failed, THE Workflow SHALL report an overall failed outcome.

### Requirement 6: Bind Provision Job to the dev GitHub Environment

**User Story:** As a platform engineer, I want every provision job scoped to the `dev` GitHub Environment, so that the job resolves the correct environment-scoped secrets and variables.

#### Acceptance Criteria

1. WHEN a Provision_Job runs, THE Provision_Job SHALL bind to the GitHub_Environment named `dev` regardless of the Leaf_Unit path.
2. THE Provision_Job SHALL resolve secrets and variables exclusively from the `dev` GitHub_Environment.
3. THE Provision_Job SHALL read the secrets `TOKEN`, `SECURITY_KEY`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY`, and the variables `AWS_REGION` and `TG_STATE_BUCKET`, from the `dev` GitHub_Environment.
4. IF any required secret or variable is missing or empty in the `dev` GitHub_Environment, THEN THE Provision_Job SHALL fail with an error indication identifying the missing value.

### Requirement 7: Provide Terragrunt Backend Configuration

**User Story:** As a platform engineer, I want the required environment variables set before Terragrunt runs, so that the root configuration can resolve the remote state backend and AWS provider.

#### Acceptance Criteria

1. WHEN a Provision_Job runs Terragrunt, THE Provision_Job SHALL set the environment variable `TG_STATE_BUCKET` to the value of the GitHub_Environment variable `TG_STATE_BUCKET`.
2. WHEN a Provision_Job runs Terragrunt, THE Provision_Job SHALL set the environment variable `AWS_REGION` to the value of the GitHub_Environment variable `AWS_REGION`.
3. IF the variable `TG_STATE_BUCKET` is unset or empty in the bound GitHub_Environment, THEN THE Provision_Job SHALL terminate with a non-zero exit status and an error indication before any Terragrunt backend initialization occurs.
4. IF the variable `AWS_REGION` is unset or empty in the bound GitHub_Environment, THEN THE Provision_Job SHALL terminate with a non-zero exit status and an error indication before any Terragrunt backend initialization occurs.
5. IF required backend configuration is missing, THEN THE Provision_Job SHALL make no changes to remote state.

### Requirement 8: Configure AWS Credentials

**User Story:** As a platform engineer, I want AWS credentials made available to Terragrunt, so that the provisioning run can access the S3 remote state and provision AWS resources.

#### Acceptance Criteria

1. WHEN a Provision_Job runs Terragrunt, THE Provision_Job SHALL set the environment variable `AWS_ACCESS_KEY_ID` to the value of the GitHub_Environment secret `AWS_ACCESS_KEY_ID`.
2. WHEN a Provision_Job runs Terragrunt, THE Provision_Job SHALL set the environment variable `AWS_SECRET_ACCESS_KEY` to the value of the GitHub_Environment secret `AWS_SECRET_ACCESS_KEY`.
3. WHEN a Provision_Job runs Terragrunt, THE Provision_Job SHALL set the environment variable `AWS_REGION` for the AWS credentials session to the value of the GitHub_Environment variable `AWS_REGION`.
4. IF the GitHub_Environment secret `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` is unset or an empty string when a Provision_Job runs Terragrunt, THEN THE Provision_Job SHALL terminate with a non-zero exit status before invoking any Terragrunt command and emit an error message identifying the missing credential.
5. IF the GitHub_Environment variable `AWS_REGION` is unset or an empty string when a Provision_Job runs Terragrunt, THEN THE Provision_Job SHALL terminate with a non-zero exit status before invoking any Terragrunt command and emit an error message indicating the region is not configured.
6. THE Provision_Job SHALL NOT record the values of `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` in job logs in plaintext.

### Requirement 9: Authenticate to Private Modules Repository

**User Story:** As a platform engineer, I want Git authentication selected based on the module source scheme, so that Terragrunt can fetch the source modules whether the leaf unit references them over HTTPS or SSH.

#### Acceptance Criteria

1. WHEN a Provision_Job runs, THE Provision_Job SHALL determine the Source_Scheme by inspecting the Terragrunt `source` declared in the changed Leaf_Unit before executing `terragrunt init`.
2. IF the Source_Scheme is the HTTPS form (`git::https://...`), THEN THE Provision_Job SHALL configure Git authentication for the Modules_Repository using the GitHub_Environment secret `TOKEN` via a token-credential URL rewrite.
3. IF the Source_Scheme is the SSH form (`git::git@...`), THEN THE Provision_Job SHALL configure Git authentication for the Modules_Repository using the GitHub_Environment secret `SECURITY_KEY` as the SSH private key.
4. IF the Source_Scheme is the HTTPS form and the secret `TOKEN` is unset or empty in the bound GitHub_Environment, THEN THE Provision_Job SHALL terminate before executing `terragrunt init`, emit an error message indicating the `TOKEN` secret is missing, and make no changes to Git configuration.
5. IF the Source_Scheme is the SSH form and the secret `SECURITY_KEY` is unset or empty in the bound GitHub_Environment, THEN THE Provision_Job SHALL terminate before executing `terragrunt init`, emit an error message indicating the `SECURITY_KEY` secret is missing, and make no changes to Git or SSH configuration.
6. IF the Provision_Job attempts to fetch the Modules_Repository and authentication is rejected, THEN THE Provision_Job SHALL fail with a non-zero exit status and emit an error message indicating that authentication to the Modules_Repository failed.
7. WHILE the `TOKEN` or `SECURITY_KEY` secret value is present in the Provision_Job, THE Provision_Job SHALL exclude the raw secret value from all emitted log output.

### Requirement 10: Run Terragrunt Against the Leaf Unit

**User Story:** As a platform engineer, I want the Workflow to run Terragrunt against each changed leaf unit, so that the tenant platform is provisioned to reflect the merged change.

#### Acceptance Criteria

1. WHEN a Provision_Job runs, THE Provision_Job SHALL execute Terragrunt with its working directory set to the `<tenant>/<env>` path corresponding to the changed Leaf_Unit.
2. WHEN a Provision_Job executes Terragrunt, THE Provision_Job SHALL run `terragrunt init` and, only if `terragrunt init` completes with a zero exit code, subsequently run `terragrunt apply`.
3. IF `terragrunt init` completes with a non-zero exit code, THEN THE Provision_Job SHALL skip `terragrunt apply` and report the Provision_Job as failed with an error indication identifying the failed init step.
4. WHEN a Provision_Job runs `terragrunt apply`, THE Provision_Job SHALL run the apply in non-interactive mode with automatic approval enabled so that no manual approval input is requested.
5. WHEN `terragrunt apply` completes with a zero exit code, THE Provision_Job SHALL report the Provision_Job as successful.
6. IF `terragrunt apply` completes with a non-zero exit code, THEN THE Provision_Job SHALL report the Provision_Job as failed with an error indication identifying the failed apply step.

### Requirement 11: Per-Job Failure Handling

**User Story:** As a platform engineer, I want failures surfaced per job with clear status, so that I can identify which tenant or environment failed to provision.

#### Acceptance Criteria

1. IF `terragrunt init` exits with a non-zero exit code, THEN THE Provision_Job SHALL fail and report the failing Leaf_Unit path in the form `<tenant>/<env>` together with an error indication.
2. IF `terragrunt apply` exits with a non-zero exit code, THEN THE Provision_Job SHALL fail and report the failing Leaf_Unit path in the form `<tenant>/<env>` together with an error indication.
3. IF a Provision_Job fails, THEN THE Workflow SHALL continue running all remaining Provision_Job runs to completion.
4. WHEN all Provision_Job runs have completed and at least one has failed, THE Workflow SHALL report an overall failed status.
5. WHEN all Provision_Job runs have completed with success, THE Workflow SHALL report an overall successful status.
