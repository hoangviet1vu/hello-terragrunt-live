# Requirements Document

## Introduction

This feature establishes the initial Terragrunt live infrastructure for the hello-terragrunt-live repository. It includes a root `terragrunt.hcl` file that configures the shared remote state backend (S3) and AWS provider, plus the first tenant ("EXAMPLE") with a single "dev" environment. The dev environment enables ECR and disables DynamoDB.

## Glossary

- **Root_Config**: The top-level `terragrunt.hcl` file at the repository root that defines the shared remote state backend (S3) and AWS provider configuration inherited by all leaf units.
- **Leaf_Unit**: A per-environment `terragrunt.hcl` file inside a tenant/environment folder that includes the Root_Config and specifies the module source and environment-specific inputs.
- **Tenant_Folder**: An uppercase-named directory at the repository root representing a single tenant (e.g., `EXAMPLE/`).
- **Environment_Folder**: A lowercase-named subdirectory within a Tenant_Folder representing a deployment environment (e.g., `dev/`).
- **State_Backend**: The S3 bucket used by Terragrunt/Terraform to store remote state files, with state keys derived from the folder path.
- **Modules_Repo**: The external Git repository (https://github.com/hoangviet1vu/hello-terragrunt-modules) containing reusable Terraform modules referenced by Leaf_Units.
- **Gitignore_File**: The `.gitignore` file at the repository root that specifies files and patterns to be excluded from version control.
- **TG_STATE_BUCKET**: An environment variable that supplies the S3 bucket name used by the Root_Config for remote state storage, allowing different users and environments to target their own state bucket without modifying the configuration file.
- **AWS_REGION**: An environment variable that supplies the AWS region used by the Root_Config for both the remote state backend and the generated AWS provider block, allowing different users and environments to target their own region without modifying the configuration file.
- **AGENTS_File**: The `AGENTS.md` file at the repository root that provides AI agents with project context, conventions, and operational instructions.
- **README_File**: The `README.md` file at the repository root that provides human developers with project overview, setup instructions, and usage guidance.

## Requirements

### Requirement 1: Root Terragrunt Configuration

**User Story:** As an infrastructure engineer, I want a root `terragrunt.hcl` that configures the S3 remote state backend and AWS provider, so that all tenant environments inherit a consistent state management and provider setup.

#### Acceptance Criteria

1. THE Root_Config SHALL define a remote state configuration using the S3 backend with bucket name sourced from the `TG_STATE_BUCKET` environment variable and region sourced from the `AWS_REGION` environment variable.
2. THE Root_Config SHALL derive the state file key using `path_relative_to_include()` appended with `/terraform.tfstate`, producing keys matching the pattern `<tenant-id>/<env>/terraform.tfstate`.
3. THE Root_Config SHALL generate a `provider.tf` file containing an AWS provider block whose region is read from the `AWS_REGION` environment variable using the `get_env()` function.
4. THE Root_Config SHALL reside at the repository root as `terragrunt.hcl`.
5. THE Root_Config SHALL enable server-side encryption for the S3 remote state backend.
6. THE Root_Config SHALL read the AWS region from the `AWS_REGION` environment variable using the Terragrunt `get_env()` function for both the remote state configuration and the generated provider block.

### Requirement 2: Tenant Folder Structure

**User Story:** As an infrastructure engineer, I want a tenant folder named "EXAMPLE", so that I have an isolated namespace for the EXAMPLE tenant's infrastructure.

#### Acceptance Criteria

1. THE Tenant_Folder SHALL be a directory named using the uppercase tenant identifier `EXAMPLE`.
2. THE Tenant_Folder SHALL be located at the repository root alongside the Root_Config.
3. THE Tenant_Folder SHALL exclusively contain Environment_Folders (lowercase-named subdirectories) representing deployment environments.

### Requirement 3: Dev Environment Leaf Unit

**User Story:** As an infrastructure engineer, I want a dev environment under the EXAMPLE tenant with ECR enabled and DynamoDB disabled, so that I can deploy tenant-specific resources for development.

#### Acceptance Criteria

1. THE Leaf_Unit SHALL reside at `EXAMPLE/dev/terragrunt.hcl`.
2. THE Leaf_Unit SHALL include the Root_Config using a relative `include` block with `path` set to `find_in_parent_folders()`.
3. THE Leaf_Unit SHALL specify the module source as a git URL in the format `git::https://github.com/hoangviet1vu/hello-terragrunt-modules.git//<module-path>?ref=v<MAJOR>.<MINOR>.<PATCH>` with a pinned semantic version tag.
4. THE Leaf_Unit SHALL pass the input `tenant_name` with the value `EXAMPLE`.
5. THE Leaf_Unit SHALL pass the input `environment` with the value `dev`.
6. THE Leaf_Unit SHALL pass the input `enable_dynamodb` with the value `false`.
7. THE Leaf_Unit SHALL pass the input `enable_ecr` with the value `true`.

### Requirement 4: State Isolation

**User Story:** As an infrastructure engineer, I want each tenant/environment combination to have an isolated state file path, so that environments do not interfere with each other.

#### Acceptance Criteria

1. WHEN any Leaf_Unit is executed, THE State_Backend SHALL store the state at a key following the pattern `<tenant-id>/<env>/terraform.tfstate` within the configured S3 bucket (e.g., `EXAMPLE/dev/terraform.tfstate` for the EXAMPLE tenant's dev environment).
2. THE Root_Config SHALL use `path_relative_to_include()` to automatically derive state keys from the folder hierarchy, ensuring the key matches the Leaf_Unit's relative path from the repository root.
3. THE State_Backend SHALL produce a unique state key for each distinct Tenant_Folder and Environment_Folder combination, such that no two Leaf_Units share the same state file path.


### Requirement 5: Gitignore Excludes Terraform State Files

**User Story:** As an infrastructure engineer, I want Terraform state files excluded from version control via `.gitignore`, so that sensitive state data is managed exclusively in S3 and never accidentally committed to the repository.

#### Acceptance Criteria

1. THE Gitignore_File SHALL include the pattern `*.tfstate` to exclude all Terraform state files from version control.
2. THE Gitignore_File SHALL include the pattern `*.tfstate.*` to exclude all Terraform state backup files from version control.
3. THE Gitignore_File SHALL include the pattern `.terraform.tfstate.lock.info` to exclude transient state lock files from version control.
4. THE Gitignore_File SHALL reside at the repository root alongside the Root_Config.
5. THE Gitignore_File SHALL include the pattern `.terraform/` to exclude the local Terraform cache directory containing provider plugins and cached state files.

### Requirement 6: Configurable S3 State Bucket via Environment Variable

**User Story:** As an infrastructure engineer, I want the S3 state bucket name read from an environment variable rather than hardcoded in the Root_Config, so that different users and environments can point to their own state bucket without modifying shared configuration files.

#### Acceptance Criteria

1. THE Root_Config SHALL read the S3 state bucket name from the environment variable `TG_STATE_BUCKET` using the Terragrunt `get_env()` function.
2. THE Root_Config SHALL NOT hardcode the S3 state bucket name as a literal string or local value within the file.
3. IF the environment variable `TG_STATE_BUCKET` is not set or is set to an empty string, THEN THE Root_Config SHALL fail with a descriptive error indicating that the `TG_STATE_BUCKET` environment variable is required.
4. WHEN a user sets the `TG_STATE_BUCKET` environment variable to a valid S3 bucket name, THE Root_Config SHALL use that value as the bucket parameter in the remote state configuration.

### Requirement 7: Documentation of State Management Configuration

**User Story:** As a developer (human or AI agent), I want the state management approach and required environment variables documented in both README.md and AGENTS.md, so that I can correctly configure the `TG_STATE_BUCKET` and `AWS_REGION` environment variables before running Terragrunt commands.

#### Acceptance Criteria

1. THE README_File SHALL document that remote state storage uses a pre-existing S3 bucket that is not created or managed by Terragrunt, and must be provisioned separately before running any Terragrunt commands.
2. THE README_File SHALL document the `TG_STATE_BUCKET` environment variable, including: its purpose (supplying the S3 bucket name for remote state), that it is required, and a shell command example showing how to set it (e.g., `export TG_STATE_BUCKET=<bucket-name>`) before running Terragrunt commands.
3. THE AGENTS_File SHALL document that remote state storage uses a pre-existing S3 bucket that is not created or managed by Terragrunt, and must be provisioned separately before running any Terragrunt commands.
4. THE AGENTS_File SHALL document the `TG_STATE_BUCKET` environment variable, including: its purpose (supplying the S3 bucket name for remote state), that it is required, and a shell command example showing how to set it (e.g., `export TG_STATE_BUCKET=<bucket-name>`) before running Terragrunt commands.
5. THE README_File SHALL reside at the repository root.
6. THE AGENTS_File SHALL reside at the repository root.
7. THE README_File SHALL document the `AWS_REGION` environment variable, including: its purpose (supplying the AWS region for both the remote state backend and the AWS provider), that it is required, and a shell command example showing how to set it (e.g., `export AWS_REGION=ap-southeast-2`) before running Terragrunt commands.
8. THE AGENTS_File SHALL document the `AWS_REGION` environment variable, including: its purpose (supplying the AWS region for both the remote state backend and the AWS provider), that it is required, and a shell command example showing how to set it (e.g., `export AWS_REGION=ap-southeast-2`) before running Terragrunt commands.

### Requirement 8: Configurable AWS Region via Environment Variable

**User Story:** As an infrastructure engineer, I want the AWS region read from an environment variable rather than hardcoded in the Root_Config, so that different users and environments can target their own AWS region without modifying shared configuration files.

#### Acceptance Criteria

1. THE Root_Config SHALL read the AWS region from the environment variable `AWS_REGION` using the Terragrunt `get_env()` function.
2. THE Root_Config SHALL NOT hardcode the AWS region as a literal string or local value within the file.
3. IF the environment variable `AWS_REGION` is not set or is set to an empty string, THEN THE Root_Config SHALL fail with a descriptive error indicating that the `AWS_REGION` environment variable is required.
4. WHEN a user sets the `AWS_REGION` environment variable to a valid AWS region identifier, THE Root_Config SHALL use that value as the region parameter in both the remote state configuration and the generated AWS provider block.
