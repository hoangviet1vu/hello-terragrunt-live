#!/usr/bin/env bash
#
# configure_module_auth.sh -- Configure Git authentication for the private
# Modules_Repository based on the Source_Scheme declared in a leaf Terragrunt
# unit. This is the "Configure module auth by scheme" provision step from the
# terragrunt-pr-merge-workflow design (Auth handling section).
#
# Behavior (Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.7):
#   - Read the leaf `source` from the file named by $LEAFPATH and classify its
#     transport prefix (matching detect_leaves.classify_source semantics):
#       git::https://          -> https
#       git::git@ | git::ssh://-> ssh
#       anything else          -> unrecognized
#   - HTTPS: require $TOKEN (fail before any git config change with a "TOKEN
#     missing" error if empty); configure a credential URL rewrite:
#       git config --global url."https://<TOKEN>@github.com/".insteadOf \
#         "https://github.com/"
#   - SSH: require $SECURITY_KEY (fail before any change with a "SECURITY_KEY
#     missing" error if empty); write the key to <ssh-dir>/id_ed25519 with mode
#     600 and add a github.com known_hosts entry.
#   - unrecognized: fail with "unrecognized source scheme"; make no change.
#   - The scheme is classified and the required secret validated BEFORE any git
#     or SSH configuration change is made, so a missing secret or unrecognized
#     scheme leaves Git/SSH configuration untouched.
#   - Secret values ($TOKEN, $SECURITY_KEY) are never echoed.
#
# Inputs (environment variables):
#   LEAFPATH       (required) Path to the changed leaf terragrunt.hcl file.
#   TOKEN          (secret)   GitHub token, required for the HTTPS scheme.
#   SECURITY_KEY   (secret)   SSH private key, required for the SSH scheme.
#
# Testability hooks (optional; keep faithful to the design when unset):
#   MODULE_AUTH_HOME     Overrides $HOME for locating the ~/.ssh directory.
#                        Defaults to $HOME.
#   MODULE_AUTH_SSH_DIR  Overrides the SSH directory outright. Defaults to
#                        "$MODULE_AUTH_HOME/.ssh".
#   MODULE_AUTH_GIT      The git command used for config (allows a stub/dry-run
#                        recorder in tests). Defaults to "git".
#   MODULE_AUTH_KEYSCAN  The command used to obtain known_hosts entries for
#                        github.com. Defaults to "ssh-keyscan github.com". Its
#                        stdout is appended to <ssh-dir>/known_hosts.
#
# Exit codes:
#   0  auth configured for the detected scheme
#   1  usage error, missing required secret, or unrecognized scheme (no change)

set -euo pipefail

err() {
	# Emit a GitHub Actions error annotation. Never include secret values.
	printf '::error::%s\n' "$1" >&2
}

main() {
	local leafpath="${LEAFPATH:-}"
	if [ -z "$leafpath" ]; then
		err "LEAFPATH is unset or empty"
		return 1
	fi
	if [ ! -f "$leafpath" ]; then
		err "leaf file not found: ${leafpath}"
		return 1
	fi

	# Extract the git:: source declaration from the leaf. This mirrors the
	# design's `grep -oE 'git::[^"]+'` extraction and takes the first match.
	local src
	src="$(grep -oE 'git::[^"]+' "$leafpath" | head -n1 || true)"
	if [ -z "$src" ]; then
		err "no git:: source found in ${leafpath}"
		return 1
	fi

	# Classify the transport prefix, matching detect_leaves.classify_source.
	local scheme
	case "$src" in
	git::https://*)
		scheme="https"
		;;
	git::git@* | git::ssh://*)
		scheme="ssh"
		;;
	*)
		scheme="unrecognized"
		;;
	esac

	local git_cmd="${MODULE_AUTH_GIT:-git}"

	case "$scheme" in
	https)
		# Validate the required secret BEFORE any git config change (Req 9.4).
		if [ -z "${TOKEN:-}" ]; then
			err "TOKEN secret missing"
			return 1
		fi
		# Configure a credential URL rewrite. The token is passed as an
		# argument to git config and is never echoed by this script.
		$git_cmd config --global \
			"url.https://${TOKEN}@github.com/.insteadOf" \
			"https://github.com/"
		printf 'Configured HTTPS token credential rewrite for github.com\n'
		;;
	ssh)
		# Validate the required secret BEFORE any SSH change (Req 9.5).
		if [ -z "${SECURITY_KEY:-}" ]; then
			err "SECURITY_KEY secret missing"
			return 1
		fi
		local home_dir ssh_dir key_file known_hosts keyscan_cmd
		home_dir="${MODULE_AUTH_HOME:-${HOME:-}}"
		ssh_dir="${MODULE_AUTH_SSH_DIR:-${home_dir}/.ssh}"
		key_file="${ssh_dir}/id_ed25519"
		known_hosts="${ssh_dir}/known_hosts"

		mkdir -p "$ssh_dir"
		chmod 700 "$ssh_dir"
		# Write the private key, then lock it down to 0600. Create it with a
		# restrictive umask so it is never briefly world-readable.
		(
			umask 077
			printf '%s\n' "$SECURITY_KEY" >"$key_file"
		)
		chmod 600 "$key_file"

		# Add a github.com known_hosts entry so the first fetch is not blocked
		# by host-key verification.
		keyscan_cmd="${MODULE_AUTH_KEYSCAN:-ssh-keyscan github.com}"
		if $keyscan_cmd >>"$known_hosts" 2>/dev/null; then
			chmod 600 "$known_hosts"
		else
			err "failed to obtain github.com host key"
			return 1
		fi
		printf 'Installed SSH key and github.com known_hosts entry\n'
		;;
	*)
		# Unrecognized scheme: fail before making any change (Req 9.1).
		err "unrecognized source scheme"
		return 1
		;;
	esac

	return 0
}

main "$@"
