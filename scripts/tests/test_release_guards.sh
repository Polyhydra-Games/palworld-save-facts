#!/usr/bin/env bash
# Non-publishing tests for check-no-overwrite.sh and recheck-release-tag.sh
# using stub gh/docker binaries and a throwaway bare remote.
set -euo pipefail
scripts="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
fails=0
check() { # check ok|fail label cmd...
  local want="$1" label="$2" rc=0; shift 2
  "$@" >/dev/null 2>&1 || rc=$?
  if { [[ $want == ok && $rc -eq 0 ]] || [[ $want == fail && $rc -ne 0 ]]; }; then echo "PASS $label"
  else echo "FAIL $label (rc=$rc, wanted $want)"; fails=$((fails+1)); fi
}

# --- stubs: STUB_MODE = exists | missing | error
bin="$work/bin"; mkdir "$bin"
cat > "$bin/gh" <<'S'
#!/usr/bin/env bash
case "$STUB_MODE" in
  exists) echo "title: v1"; exit 0;;
  missing) echo "release not found" >&2; exit 1;;
  *) echo "HTTP 502 bad gateway" >&2; exit 1;;
esac
S
cat > "$bin/docker" <<'S'
#!/usr/bin/env bash
case "$STUB_MODE" in
  exists) echo '{}'; exit 0;;
  missing) echo "no such manifest: ghcr.io/o/n:v1.0.0" >&2; exit 1;;
  *) echo "unauthorized" >&2; exit 1;;
esac
S
chmod +x "$bin/gh" "$bin/docker"
export PATH="$bin:$PATH" IMAGE=ghcr.io/o/n RELEASE_TAG=v1.0.0
no="$scripts/check-no-overwrite.sh"
for kind in release image; do
  STUB_MODE=missing check ok "$kind missing -> ok" bash "$no" $kind
  STUB_MODE=exists  check fail "$kind exists -> refused" bash "$no" $kind
  STUB_MODE=exists ALLOW_OVERWRITE=true check ok "$kind exists + allow_overwrite" bash "$no" $kind
  STUB_MODE=exists ALLOW_OVERWRITE=false check fail "$kind exists + allow_overwrite=false" bash "$no" $kind
  STUB_MODE=error   check fail "$kind probe error -> fail closed" bash "$no" $kind
  STUB_MODE=error ALLOW_OVERWRITE=true check fail "$kind probe error ignores allow" bash "$no" $kind
done
STUB_MODE=missing check fail "bad tag" env RELEASE_TAG='v1.0.0;id' bash "$no" release
STUB_MODE=missing check fail "bad kind" bash "$no" bogus

# --- recheck against a bare remote
remote="$work/remote.git"; src="$work/src"
git init -q --bare "$remote"
git init -q -b main "$src"; cd "$src"
git config user.email t@t; git config user.name t
git commit -q --allow-empty -m one; one="$(git rev-parse HEAD)"
git commit -q --allow-empty -m two; two="$(git rev-parse HEAD)"
git tag v1.0.0 "$one"; git tag -a v2.0.0 -m ann "$one"
git remote add origin "$remote"; git push -q origin main --tags
rc="$scripts/recheck-release-tag.sh"
export REMOTE="$remote"
check ok   "lightweight tag unchanged" env RELEASE_TAG=v1.0.0 VERIFIED_SHA="$one" bash "$rc"
check ok   "annotated tag unchanged (peeled)" env RELEASE_TAG=v2.0.0 VERIFIED_SHA="$one" bash "$rc"
check fail "wrong verified sha" env RELEASE_TAG=v1.0.0 VERIFIED_SHA="$two" bash "$rc"
check fail "annotated wrong sha" env RELEASE_TAG=v2.0.0 VERIFIED_SHA="$two" bash "$rc"
check fail "missing tag" env RELEASE_TAG=v3.0.0 VERIFIED_SHA="$one" bash "$rc"
check fail "non-hex sha" env RELEASE_TAG=v1.0.0 VERIFIED_SHA=abc bash "$rc"
git push -q --force origin "$two:refs/tags/v1.0.0"   # move the tag
check fail "lightweight tag moved" env RELEASE_TAG=v1.0.0 VERIFIED_SHA="$one" bash "$rc"
git tag -f -a v2.0.0 -m moved "$two" >/dev/null; git push -q --force origin refs/tags/v2.0.0
check fail "annotated tag moved" env RELEASE_TAG=v2.0.0 VERIFIED_SHA="$one" bash "$rc"
check ok   "moved tag matches new sha" env RELEASE_TAG=v2.0.0 VERIFIED_SHA="$two" bash "$rc"
# --- guards run from a directory with no scripts/ tree and no git remote
bare="$work/elsewhere"; mkdir "$bare"; (cd "$bare" && git init -q .)
cd "$bare"
[[ ! -e scripts ]] || { echo "FAIL setup"; fails=$((fails+1)); }
STUB_MODE=missing check ok "no-tree cwd: release absent" env RELEASE_TAG=v1.0.0 bash "$no" release
STUB_MODE=exists  check fail "no-tree cwd: release exists" env RELEASE_TAG=v1.0.0 bash "$no" release
check ok   "no-tree cwd: recheck via REMOTE url" env REMOTE="$remote" RELEASE_TAG=v2.0.0 VERIFIED_SHA="$two" bash "$rc"
check fail "no-tree cwd: recheck mismatch" env REMOTE="$remote" RELEASE_TAG=v2.0.0 VERIFIED_SHA="$one" bash "$rc"
[[ $fails -eq 0 ]] || { echo "$fails failure(s)"; exit 1; }
echo "all release guard tests passed"
