#!/usr/bin/env bash
#
# validate_entry.sh - Validate a single provision matrix entry before provisioning.
#
# Feature: terragrunt-pr-merge-workflow
# Requirements: 4.4 (malformed path), 5.6 (missing/empty tenant/workDir/leafPath)
# Design: "Validate matrix entry step" / Path_Parser
#
# Reads TENANT, WORKDIR, LEAFPATH from environment variables. For convenience and
# testability, positional arguments override the environment values when provided,
# in the order: TENANT WORKDIR LEAFPATH.
#
# Fails (non-zero exit) with an identifying `::error::` message when:
#   - any of TENANT, WORKDIR, or LEAFPATH is empty (Req 5.6), or
#   - LEAFPATH is malformed: fewer than two directory segments before the
#     filename, i.e. it is not of the form <seg>/<seg>/.../<file> (Req 4.4).
#
# On success, emits nothing and exits 0.

set -euo pipefail

# Positional args override env vars when supplied.
TENANT="${1:-${TENANT:-}}"
WORKDIR="${2:-${WORKDIR:-}}"
LEAFPATH="${3:-${LEAFPATH:-}}"

# --- Missing/empty field checks (Req 5.6) -----------------------------------
if [ -z "$TENANT" ]; then
  echo "::error::missing tenant"
  exit 1
fi
if [ -z "$WORKDIR" ]; then
  echo "::error::missing workDir"
  exit 1
fi
if [ -z "$LEAFPATH" ]; then
  echo "::error::missing leafPath"
  exit 1
fi

# --- Malformed path check (Req 4.4) -----------------------------------------
# A well-formed leaf path has at least two directory segments before the
# filename: <tenant>/<env>/<file>. Count the number of '/' separators; two or
# more separators means at least two leading directory segments.
#
# Guard against leading '/', trailing '/', or empty segments (e.g. "a//b") which
# would not represent a real "<tenant>/<env>/<file>" leaf.
case "$LEAFPATH" in
  /*)
    echo "::error::leafPath is malformed: $LEAFPATH"
    exit 1
    ;;
  */)
    echo "::error::leafPath is malformed: $LEAFPATH"
    exit 1
    ;;
esac

if [[ "$LEAFPATH" == *"//"* ]]; then
  echo "::error::leafPath is malformed: $LEAFPATH"
  exit 1
fi

# Count the leading directory segments (everything before the final filename).
dir="${LEAFPATH%/*}"
if [ "$dir" = "$LEAFPATH" ]; then
  # No '/' at all: single-segment path, no leading directories.
  echo "::error::leafPath is malformed: $LEAFPATH"
  exit 1
fi

# Number of directory segments = number of '/' in "$LEAFPATH".
slashes="${LEAFPATH//[^\/]/}"
if [ "${#slashes}" -lt 2 ]; then
  echo "::error::leafPath is malformed: $LEAFPATH"
  exit 1
fi

exit 0
