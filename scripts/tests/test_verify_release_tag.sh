#!/usr/bin/env bash
# Non-publishing test for scripts/verify-release-tag.sh using a throwaway repo.
set -euo pipefail
script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/verify-release-tag.sh"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
cd "$work"
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
git init -q -b main . && git config user.email t@t && git config user.name t
git commit -q --allow-empty -m one
git tag v1.0.0
git commit -q --allow-empty -m two
git tag -a v1.1.0-rc.1 -m annotated
main_sha="$(git rev-parse main)"
git checkout -q -b side && git commit -q --allow-empty -m side && git tag v9.9.9
git checkout -q main
export MAIN_REF=main
fails=0
expect() { # expect ok|fail <tag> [expected_sha]
  local want="$1" tag="$2" exp="${3:-}" rc=0
  RELEASE_TAG="$tag" EXPECTED_SHA="$exp" bash "$script" >/dev/null 2>&1 || rc=$?
  if { [[ $want == ok && $rc -eq 0 ]] || [[ $want == fail && $rc -ne 0 ]]; }; then
    echo "PASS $want '$tag'"
  else echo "FAIL expected $want for '$tag' (rc=$rc)"; fails=$((fails+1)); fi
}
expect ok v1.0.0
expect ok v1.1.0-rc.1
expect ok v1.1.0-rc.1 "$main_sha"
expect fail v1.0.0 "$main_sha"          # sha mismatch
expect fail v9.9.9                      # not reachable from main
expect fail v2.0.0                      # missing tag
expect fail ""                          # empty
expect fail 1.0.0                       # no v prefix
expect fail v1.0                        # not semver
expect fail 'v1.0.0;id'                 # injection
expect fail 'v1.0.0 '                   # whitespace
expect fail $'v1.0.0\nx'                # newline
expect fail main                        # branch name
expect fail refs/tags/v1.0.0
out="$work/out"; RELEASE_TAG=v1.0.0 GITHUB_OUTPUT="$out" bash "$script" >/dev/null
grep -q '^tag=v1.0.0$' "$out" && grep -q '^sha=' "$out" || { echo "FAIL outputs"; fails=$((fails+1)); }
[[ $fails -eq 0 ]] || { echo "$fails failure(s)"; exit 1; }
echo "all verify-release-tag tests passed"
