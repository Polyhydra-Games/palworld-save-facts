#!/usr/bin/env bash
# Refuse to re-release a tag: fail if a GitHub release or GHCR image tag
# already exists, unless ALLOW_OVERWRITE=true. Fails closed on probe errors.
#
# Usage: check-no-overwrite.sh release|image
# Inputs (environment only):
#   RELEASE_TAG      tag to probe (required)
#   ALLOW_OVERWRITE  "true" to permit an existing release/image (default false)
#   GH_TOKEN/GH_REPO used by `gh release view` (kind=release)
#   IMAGE            image repository without tag, e.g. ghcr.io/owner/name (kind=image)
set -euo pipefail

kind="${1:-}"
tag="${RELEASE_TAG:-}"
allow="${ALLOW_OVERWRITE:-false}"

fail() { echo "check-no-overwrite: $*" >&2; exit 1; }

[[ -n "$tag" ]] || fail "RELEASE_TAG is empty"
re='^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$'
[[ "$tag" =~ $re ]] || fail "tag '$tag' does not match $re"

case "$kind" in
  release)
    what="GitHub release for $tag"
    absent_re='release not found'
    probe=(gh release view "$tag")
    ;;
  image)
    [[ -n "${IMAGE:-}" ]] || fail "IMAGE is empty"
    what="image ${IMAGE}:$tag"
    absent_re='no such manifest|manifest unknown|not found'
    probe=(docker manifest inspect "${IMAGE}:${tag}")
    ;;
  *) fail "usage: check-no-overwrite.sh release|image" ;;
esac

rc=0
out="$("${probe[@]}" 2>&1)" || rc=$?
if [[ $rc -eq 0 ]]; then
  if [[ "$allow" == "true" ]]; then
    echo "check-no-overwrite: $what exists; allow_overwrite=true, continuing" >&2
    exit 0
  fi
  fail "$what already exists; releases are immutable (set allow_overwrite to override)"
fi
if grep -Eqi "$absent_re" <<<"$out"; then
  echo "check-no-overwrite: $what does not exist"
  exit 0
fi
fail "could not determine whether $what exists (probe exit $rc): ${out:0:200}"
