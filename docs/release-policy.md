# Release, update, and rollback policy

`palworld-save-facts` releases are operator-facing GPL executable releases.
They are not a mechanism for publishing save fixtures, decoded JSON, reports,
or restricted identifiers.

## Release evidence

Every release must attach these public artifacts:

- Linux x64, Linux arm64, Windows x64, and macOS arm64 executables;
- `SHA256SUMS.txt` and `release-manifest.json` listing the exact source commit,
  pinned decoder submodule SHA, asset hashes, OCI digest, supported schema
  range, and prior rollback version;
- SPDX SBOM, license inventory, and source/provenance attestations; and
- an OCI image that runs as a non-root user and has no save data embedded.

The release workflow may build these artifacts only from a protected tag or an
explicit owner-approved dispatch. It must never upload test fixtures, private
benchmark reports, `raw.json.zst`, normalized output, or decoder diagnostics.

## Release workflow guards

`.github/workflows/release.yml` is hardened as follows; `tests/test_release_workflow.py`
and `scripts/tests/` enforce these rules:

- The workflow default is `contents: read`; each job declares only what it
  needs (`oci` adds `packages: write`; `publish` adds `contents: write`,
  `attestations: write`, `id-token: write`).
- Every `actions/checkout` sets `persist-credentials: false`, and every
  third-party action is pinned by full commit SHA with a trailing version comment.
- Releases are immutable. `verify_tag` fails if a GitHub release for the tag
  already exists, and `oci` fails if `ghcr.io/<owner>/palworld-save-facts:<tag>`
  already exists. A probe error fails closed. The only override is the
  `workflow_dispatch` boolean input `allow_overwrite` (default `false`); tag
  pushes can never overwrite. Use it only for an owner-approved re-release or
  to resume a run whose OCI push succeeded but whose publish failed, and
  record why in the release issue.
- Guard scripts run from a separate checkout of the workflow's own revision
  (`.release-guards`), while builds and published assets come from the
  verified tag, so re-releasing a tag that predates the guards still works.
- Immediately before the GitHub release step, `publish` re-resolves the tag
  with `git ls-remote` and fails if it no longer points at the commit
  `verify_tag` verified (`scripts/recheck-release-tag.sh`).

## Private qualification limits

Before promotion, an operator runs `scripts/private_benchmark.py` on the
controlled host. Its defaults are intentionally closed:

| Limit | Value |
| --- | --- |
| Concurrent analyses | 1 |
| Wall-clock timeout | 10 minutes |
| Working set | 2 GiB |
| Raw compressed artifact | 4 GiB |
| Normalized snapshot | 128 MiB |

The benchmark writes a private report and emits only `pass` or `fail`; it does
not reveal paths, save hashes, entity counts, identifiers, or decoded values.
It uses one host-wide private temporary lock, so independently selected output
directories cannot bypass the one-analysis limit.
An OS/container memory limit remains required in production; the benchmark is
the release qualification check, not a sandbox.

## Update and rollback

1. Record the old release tag and immutable image digest before updating.
2. Verify all release-manifest hashes before installing an executable or image.
3. Qualify the candidate on private snapshots before production promotion.
4. Roll back only to the preceding release tag and digest recorded in the new
   manifest; do not substitute mutable `latest` images or unverified binaries.
5. Preserve normalized history and private raw-artifact retention policy; a
   decoder rollback must not delete either.

The v1 stdout command remains supported. v2 normalized snapshots are a stable
private-analysis contract; they do not grant a public raw-data surface or
relax the private-fixture boundary.
