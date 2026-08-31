#!/usr/bin/env bash
#
# init_apply_gate.sh
#
# Provision-step helper for the terragrunt-pr-merge-workflow. This is the
# "Terragrunt init + apply" gate from the design (Provision step, Req 10):
#
#   1. Run `terragrunt init` non-interactively.
#   2. ONLY if init exits with code 0, run
#      `terragrunt apply -auto-approve -input=false --terragrunt-non-interactive`.
#   3. If init fails, skip apply entirely and fail the leg, reporting the
#      failing `<tenant>/<env>` path.
#   4. If apply fails, fail the leg, reporting the failing `<tenant>/<env>` path.
#
# The gate guarantees `apply` never runs after a failed `init`, so a broken
# backend or module fetch never proceeds to mutate infrastructure.
#
# Requirements: 10.2, 10.3, 10.4, 10.5, 10.6, 11.1, 11.2
#
# Inputs (environment variables):
#   WORKDIR        (required) The `<tenant>/<env>` path for the changed leaf.
#                  Used only in error annotations. Note: the actual working
#                  directory is expected to already be set by the caller (the
#                  workflow uses `working-directory: ${{ matrix.workDir }}`);
#                  this script does NOT cd into WORKDIR so it stays faithful to
#                  the workflow step and remains unit-testable.
#
# Testability hook (optional):
#   TERRAGRUNT_BIN The terragrunt command to invoke. Defaults to "terragrunt".
#                  Tests override this with a stub that simulates configurable
#                  init/apply exit codes without a real terragrunt install.
#
# Exit codes:
#   0  init succeeded and apply succeeded
#   1  usage error, init failure (apply skipped), or apply failure

set -euo pipefail

err() {
	# Emit a GitHub Actions error annotation on stderr.
	printf '::error::%s\n' "$1" >&2
}

main() {
	local workdir="${WORKDIR:-}"
	if [ -z "$workdir" ]; then
		err "WORKDIR is unset or empty"
		return 1
	fi

	local tg="${TERRAGRUNT_BIN:-terragrunt}"

	# Step 1: terragrunt init (non-interactive). If it fails, skip apply and
	# fail the leg reporting the <tenant>/<env> path (Req 10.3, 11.1).
	if ! "$tg" init -input=false --terragrunt-non-interactive; then
		err "terragrunt init failed for ${workdir}"
		return 1
	fi

	# Step 2: terragrunt apply, reached only on a zero init exit code
	# (Req 10.2). Non-interactive with automatic approval (Req 10.4). On a
	# non-zero apply exit code, fail reporting the <tenant>/<env> path
	# (Req 10.6, 11.2).
	if ! "$tg" apply -auto-approve -input=false --terragrunt-non-interactive; then
		err "terragrunt apply failed for ${workdir}"
		return 1
	fi

	# Both init and apply succeeded (Req 10.5, 11.5).
	printf 'terragrunt init + apply succeeded for %s\n' "$workdir"
	return 0
}

main "$@"
