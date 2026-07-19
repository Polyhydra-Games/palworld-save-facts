# v1 to v2 compatibility boundary

`palworld-save-facts/v1` remains the stable stdout contract. The v2 assembler
is an additive internal projection and does not alter the v1 command, schema,
ordering, or diagnostics.

## Pal mapping

The only Pal-specific v1 fact is the aggregate `palCount`. Its deterministic
v2 counterpart is `domainCounts.pals`, calculated from the ordered v2 `pals`
collection. The relationship is one-way: v1 is not reconstructed from v2.

| v1 fact | v2 counterpart | Notes |
| --- | --- | --- |
| `palCount` | `domainCounts.pals` | Both count decoded non-player character instances. |
| no instance fields | `pals[]` | v1 intentionally has no per-Pal identity, ownership, skills, traits, container, or base-assignment surface. |

V2 may retain snapshot-local identifiers and field-presence states needed for
typed private analysis. Those values are restricted and must not enter v1
stdout, normal diagnostics, browser APIs, or public fixtures. Decoder-native
objects remain raw-only.

## Intentional omissions

V1 does not gain a backfilled Pal list, cause claims (capture, breeding, trade,
or discovery), raw decoder objects, native IDs, names, positions, or v2
completeness warnings. The existing v1 player, guild, base, and aggregate facts
remain independently extracted from the original decoded input.

## Removal boundary

The v1 command and schema remain supported until a separately approved removal
issue provides a migration window, compatibility evidence, and an operator
rollback path. Adding a v2 field or schema family never changes v1 output.
