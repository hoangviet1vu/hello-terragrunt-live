---
inclusion: auto
---

# Product Context

## Purpose

This is the **hello-terragrunt-live** repository — the live infrastructure
layer for Tenant Configuration management. It defines per-tenant,
per-environment infrastructure using Terragrunt to orchestrate reusable
Terraform modules.

## Problem Statement

Each tenant requires isolated cloud resources (S3 buckets, DynamoDB tables,
ECR repositories) across multiple environments. Configuration must be
repeatable, version-controlled, and independently deployable per
tenant/environment combination.

## How It Works

- Each tenant gets a dedicated folder (uppercase tenant ID).
- Each environment within a tenant is a subfolder (`dev`, `prod`, etc.).
- Leaf `terragrunt.hcl` files pin a specific version of the shared modules
  repo and pass environment-specific inputs (feature flags, naming).
- The root `terragrunt.hcl` provides shared remote state (S3) and AWS
  provider configuration inherited by all leaves.

## Source Modules

Reusable Terraform modules live in a separate repository:
https://github.com/hoangviet1vu/hello-terragrunt-modules

The `tenant-base` module provisions:
- S3 bucket (always)
- DynamoDB table (toggle via `enable_dynamodb`)
- ECR repository (toggle via `enable_ecr`)

## Versioning Strategy

- Modules are pinned by git tag (`?ref=v1.0.0`).
- Environments are promoted independently: dev first, then prod.
- Never reference a moving branch for real environments.
