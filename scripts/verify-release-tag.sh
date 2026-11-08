#!/usr/bin/env bash
# Verify a release tag names an immutable source tag reachable from the
# release branch, and print the resolved commit. Fails closed.
#
# Inputs (environment only; never interpolate untrusted values into scripts):
#   RELEASE_TAG    candidate tag (required)
#   MAIN_REF       ref the tag commit must be reachable from (default origin/main)
#   EXPECTED_SHA   optional; if set, the tag must resolve to exactly this commit
#   GITHUB_OUTPUT  if set, "tag=" and "sha=" are appended to it
# Run inside a clone that has the tags and MAIN_REF fetched.
set -euo pipefail

tag="${RELEASE_TAG:-}"
main_ref="${MAIN_REF:-origin/main}"
expected="${EXPECTED_SHA:-}"

fail() { echo "verify-release-tag: $*" >&2; exit 1; }

[[ -n "$tag" ]] || fail "RELEASE_TAG is empty"
[[ ${#tag} -le 128 ]] || fail "tag too long"
re='^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'
[[ "$tag" =~ $re ]] || fail "tag '$tag' does not match $re"

sha="$(git rev-parse --verify --quiet "refs/tags/${tag}^{commit}")" \
  || fail "tag '$tag' does not exist as refs/tags/$tag"
git rev-parse --verify --quiet "${main_ref}^{commit}" >/dev/null \
  || fail "reference '$main_ref' not found"
git merge-base --is-ancestor "$sha" "$main_ref" \
  || fail "tag '$tag' ($sha) is not reachable from $main_ref"
if [[ -n "$expected" && "$expected" != "$sha" ]]; then
  fail "tag '$tag' resolves to $sha, expected $expected"
fi

echo "verified tag=$tag sha=$sha"
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  { echo "tag=$tag"; echo "sha=$sha"; } >> "$GITHUB_OUTPUT"
fi
