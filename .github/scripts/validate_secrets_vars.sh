#!/usr/bin/env bash
#
# validate_secrets_vars.sh
#
# Provision-step helper for the terragrunt-pr-merge-workflow.
#
# Confirms that the always-required GitHub Environment variables and secrets are
# present and non-empty *before* any Terragrunt invocation or remote-state
# access occurs. If any value is missing or empty, the script fails with a
# non-zero exit status and emits a GitHub Actions `::error::` annotation that
# names the first missing value.
#
# Always-required (validated here):
#   Variables (non-sensitive):  TG_STATE_BUCKET, AWS_REGION
#   Secrets (sensitive):        AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
#
# NOT validated here:
#   TOKEN / SECURITY_KEY are validated *conditionally by Source_Scheme* in the
#   module-auth helper, since a given leaf uses only one transport (HTTPS or
#   SSH). Validating them unconditionally would reject legitimate single-scheme
#   leaves.
#
# Secret hygiene:
#   This script reads values from the environment and NEVER echoes any value
#   (secret or otherwise). Error messages name only the missing key, never its
#   contents.
#
# Requirements: 6.3, 6.4, 7.3, 7.4, 7.5, 8.4, 8.5
#
# Usage:
#   TG_STATE_BUCKET=... AWS_REGION=... AWS_ACCESS_KEY_ID=... \
#     AWS_SECRET_ACCESS_KEY=... ./validate_secrets_vars.sh
#
# Exit codes:
#   0  all required values present and non-empty
#   1  a required value is unset or empty (first missing value is named)

set -euo pipefail

# Ordered list of required values. Order defines which value is reported first
# when multiple are missing. Variables are listed before secrets so backend
# configuration problems surface first.
REQUIRED_VALUES=(
	TG_STATE_BUCKET
	AWS_REGION
	AWS_ACCESS_KEY_ID
	AWS_SECRET_ACCESS_KEY
)

fail_missing() {
	# Name only the key; never print its value.
	local name="$1"
	echo "::error::Required value ${name} is unset or empty; refusing to run Terragrunt." >&2
	exit 1
}

main() {
	local name value
	for name in "${REQUIRED_VALUES[@]}"; do
		# Indirect expansion with a default so `set -u` does not abort on unset.
		value="${!name:-}"
		if [ -z "${value}" ]; then
			fail_missing "${name}"
		fi
	done

	# Reaching here means every required value is present and non-empty.
	echo "All required secrets and variables are present."
}

main "$@"
