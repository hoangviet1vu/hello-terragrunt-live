#!/usr/bin/env bash
#
# terragrunt_plan_dryrun.sh -- OPTIONAL / MANUAL dry-run harness for the
# terragrunt-pr-merge-workflow feature (tasks.md task 13.1).
#
# Purpose (Requirements 9.2, 9.3, 10.1):
#   Before the workflow ever runs `apply`, prove the end-to-end path with a
#   NON-MUTATING `terragrunt init` + `terragrunt plan` against a fixture leaf.
#   This confirms three things without touching real infrastructure:
#     - backend resolution        (root.hcl + TG_STATE_BUCKET/AWS_REGION -> S3)
#     - module auth by scheme      (HTTPS TOKEN rewrite / SSH SECURITY_KEY)
#     - working-directory selection (terragrunt runs in the leaf's dir, 10.1)
#
#   It runs `plan` only -- never `apply` -- so it makes no changes to infra or
#   remote state beyond what `init`/`plan` read.
#
# This harness is GATED. It requires live/network resources (private module
# repo access, AWS credentials, a state bucket) that are not available offline
# or in unit CI. When those prerequisites are missing it prints a SKIP notice
# and exits 0 so it can be wired into a pipeline harmlessly. Set
# TG_DRYRUN_STRICT=1 to make missing prerequisites a hard failure instead.
#
# Usage:
#   terragrunt_plan_dryrun.sh [https|ssh]     # default: https
#
# Required environment (checked before running):
#   Always:
#     TG_STATE_BUCKET, AWS_REGION,
#     AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
#   For the https fixture: TOKEN         (GitHub token; HTTPS module auth)
#   For the ssh fixture:   SECURITY_KEY  (SSH private key; SSH module auth)
#
# Testability hook:
#   TG_DRYRUN_TERRAGRUNT   Override the terragrunt binary (defaults to
#                          "terragrunt" on PATH). Useful for a stubbed harness.
#
# Exit codes:
#   0  plan succeeded, OR prerequisites missing and TG_DRYRUN_STRICT is unset
#   1  usage error, OR (with TG_DRYRUN_STRICT=1) missing prerequisites, OR the
#      terragrunt init/plan step failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="${SCRIPT_DIR}/tests/fixtures"

TG_BIN="${TG_DRYRUN_TERRAGRUNT:-terragrunt}"
STRICT="${TG_DRYRUN_STRICT:-}"

notice() { printf 'terragrunt_plan_dryrun: %s\n' "$1"; }
err() { printf '::error::%s\n' "$1" >&2; }

# skip_or_fail <reason>: honor strict mode.
skip_or_fail() {
	if [ -n "$STRICT" ]; then
		err "prerequisite missing (strict mode): $1"
		exit 1
	fi
	notice "SKIP: $1"
	exit 0
}

scheme="${1:-https}"
case "$scheme" in
https)
	leaf_dir="${FIXTURES_DIR}/leaves/https_source"
	;;
ssh)
	leaf_dir="${FIXTURES_DIR}/leaves/ssh_source"
	;;
*)
	err "usage: terragrunt_plan_dryrun.sh [https|ssh] (got: '${scheme}')"
	exit 1
	;;
esac

leaf_file="${leaf_dir}/terragrunt.hcl"
if [ ! -f "$leaf_file" ]; then
	err "fixture leaf not found: ${leaf_file}"
	exit 1
fi

# --- gate on tooling -----------------------------------------------------
if ! command -v "$TG_BIN" >/dev/null 2>&1; then
	skip_or_fail "terragrunt binary '${TG_BIN}' not found on PATH"
fi

# --- gate on always-required backend/credential env ----------------------
for var in TG_STATE_BUCKET AWS_REGION AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
	if [ -z "${!var:-}" ]; then
		skip_or_fail "environment variable ${var} is unset or empty"
	fi
done

# --- gate on scheme-specific module-auth secret --------------------------
case "$scheme" in
https)
	if [ -z "${TOKEN:-}" ]; then
		skip_or_fail "TOKEN (HTTPS module auth) is unset or empty"
	fi
	;;
ssh)
	if [ -z "${SECURITY_KEY:-}" ]; then
		skip_or_fail "SECURITY_KEY (SSH module auth) is unset or empty"
	fi
	;;
esac

# --- configure module auth for the detected scheme -----------------------
# Reuse the real provision-step auth helper so the dry-run exercises the same
# code path the workflow uses (Req 9.2 / 9.3). Secrets are passed via env and
# never echoed by the helper.
notice "configuring module auth (scheme=${scheme}) via configure_module_auth.sh"
LEAFPATH="$leaf_file" bash "${SCRIPT_DIR}/configure_module_auth.sh"

# --- run init + plan in the leaf's working directory ---------------------
# Setting the working directory here confirms working-directory selection
# (Req 10.1): terragrunt resolves root.hcl via find_in_parent_folders and plans
# the fixture leaf's module. No apply is performed (Req: non-mutating dry-run).
notice "running 'terragrunt init' in ${leaf_dir}"
(
	cd "$leaf_dir"
	"$TG_BIN" init -input=false --terragrunt-non-interactive
)

notice "running 'terragrunt plan' in ${leaf_dir} (no apply)"
(
	cd "$leaf_dir"
	"$TG_BIN" plan -input=false --terragrunt-non-interactive
)

notice "PASS: init + plan completed for scheme=${scheme} in ${leaf_dir}"
