#!/usr/bin/env bash
# Re-resolve a release tag on the remote and fail if it no longer points at
# the commit verified earlier (guards the window before publication).
#
# Inputs (environment only):
#   RELEASE_TAG   tag name (required)
#   VERIFIED_SHA  commit verified by verify-release-tag.sh (required)
#   REMOTE        remote name or URL (default origin)
set -euo pipefail

tag="${RELEASE_TAG:-}"
verified="${VERIFIED_SHA:-}"
remote="${REMOTE:-origin}"

fail() { echo "recheck-release-tag: $*" >&2; exit 1; }

[[ -n "$tag" ]] || fail "RELEASE_TAG is empty"
re='^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'
[[ "$tag" =~ $re ]] || fail "tag '$tag' does not match $re"
[[ "$verified" =~ ^[0-9a-f]{40}$ ]] || fail "VERIFIED_SHA is not a 40-hex commit"

lines="$(git ls-remote --tags "$remote" "refs/tags/${tag}^{}" "refs/tags/${tag}")" \
  || fail "git ls-remote failed"
# Annotated tags list a peeled ^{} line (the commit); lightweight tags only the plain line.
current="$(awk -v r="refs/tags/${tag}^{}" '$2==r{print $1}' <<<"$lines")"
if [[ -z "$current" ]]; then
  current="$(awk -v r="refs/tags/${tag}" '$2==r{print $1}' <<<"$lines")"
fi
[[ -n "$current" ]] || fail "tag '$tag' no longer exists on $remote"
[[ "$current" == "$verified" ]] \
  || fail "tag '$tag' moved: now $current, verified $verified"
echo "recheck-release-tag: tag=$tag still at $verified"
