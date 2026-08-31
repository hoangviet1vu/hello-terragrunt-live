#!/usr/bin/env bash
#
# guard_merged_state.sh -- merged-state guard for the terragrunt-pr-merge-workflow.
#
# The workflow triggers on the pull_request "closed" event. Before performing
# any change detection, it must confirm that the merged state is a determinable
# boolean. GitHub's `github.event.pull_request.merged` context is normally
# "true" or "false", but this guard fails loudly for anything else (empty,
# "null", "yes", ...) rather than silently provisioning (Req 1.5). The guard is
# evaluated before change detection (Req 1.3).
#
# Usage:
#   guard_merged_state.sh <merged-value>
#   MERGED=<merged-value> guard_merged_state.sh
#
# The merged value is taken from $1 when provided, otherwise from the MERGED
# environment variable.
#
# Exit status:
#   0  when the value is exactly "true" or "false" (merged state determinable).
#   1  otherwise, printing "::error::merged state indeterminable" to stderr.
#
# Requirements: 1.3, 1.5

set -euo pipefail

# Take the merged value from the first positional argument when supplied,
# otherwise fall back to the MERGED environment variable. Missing/unset yields
# an empty string, which is treated as indeterminable below.
merged="${1-${MERGED-}}"

case "$merged" in
true | false)
	exit 0
	;;
*)
	echo "::error::merged state indeterminable" >&2
	exit 1
	;;
esac
