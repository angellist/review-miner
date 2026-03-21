---
scope: backend
---

# Data Integrity

### Transaction Boundaries

- Wrap paired destructive-then-constructive operations (delete + create, update + insert) in a transaction
- Pass the transaction client (`tx`) to all helper functions — never use the outer prisma client inside a `$transaction` callback
- Use `ensureTransaction` wrappers so functions compose correctly inside existing transactions
- Never wrap external API calls inside interactive transactions — they hold a DB connection open for the duration

```ts
// Bad — mixes transactional and non-transactional clients
await prisma.$transaction(async (tx) => {
  await tx.record.update({ ... });
  await prisma.auditLog.create({ ... }); // uses outer client!
});

// Good
await prisma.$transaction(async (tx) => {
  await tx.record.update({ ... });
  await tx.auditLog.create({ ... });
});
```

_Sources: PR #3024, PR #3521, PR #3567, PR #3888, PR #4900, PR #5126_

### Race Conditions on Shared State

- Read-then-write on version/counter fields must use a transaction or atomic update
- Never overwrite an entire JSON/JSONB blob — read current value and merge changed fields only
- Validate dynamic keys exist before writing into JSON blobs to prevent silent orphan keys
- For stronger guarantees, use `SELECT FOR UPDATE` or field-level updates

```ts
// Bad — full-blob write causes lost updates under concurrency
await tx.item.update({ data: { metadata: newMetadata } });

// Good — merge strategy
const current = await tx.item.findUnique({ where: { id } });
await tx.item.update({
  data: { metadata: { ...current.metadata, ...changedFields } },
});
```

_Sources: PR #3132, PR #3696, PR #5277_

### Upsert Correctness

- Use upsert (or `createMany` with `skipDuplicates`) instead of plain create for sync/seed/onboarding scripts
- Verify that the fields in your upsert WHERE clause match the table's unique constraint — a mismatch silently becomes a no-op
- Prisma's upsert with an empty `update` is not truly atomic (SELECT + INSERT) — use raw `INSERT ... ON CONFLICT` for concurrent scenarios

```ts
// Bad — upsert where clause doesn't match unique constraint
await prisma.consent.upsert({
  where: { visitorId },        // unique is on (email, ip)
  create: { ... },
  update: { ... },             // never matches → always creates
});
```

_Sources: PR #6289, PR #6541, PR #3489, PR #6676_

### Bulk Operation Safety

- Batch bulk operations (create, update, delete) to avoid ORM parameter limits (~10k in Prisma)
- Validate that fetched record count matches input ID count — silently dropping invalid IDs causes partial operations that appear successful
- For backfills inside transactions, account for worst-case data volume and bump timeout or batch into separate transactions

```ts
// Bad — unbounded array blows up Prisma
await prisma.permission.deleteMany({ where: { id: { in: allIds } } });

// Good — chunk into batches
for (const batch of chunk(allIds, 5000)) {
  await prisma.permission.deleteMany({ where: { id: { in: batch } } });
}
```

_Sources: PR #2606, PR #5152, PR #5172, PR #3827_

### Dynamic Query Construction

- Guard against `OR: []` in Prisma — an empty OR array matches nothing instead of being a no-op
- When all filter parameters are optional, handle the empty-filter case explicitly (require at least one, provide a safe default, or document the behavior)
- Apply status allow-lists in the WHERE clause, not as post-filters — deny-lists break silently when new statuses are added

```ts
// Bad — empty OR returns zero results
const filters = buildOrFilters(input);
await prisma.entity.findMany({ where: { OR: filters } });

// Good
const where = filters.length > 0 ? { OR: filters } : {};
await prisma.entity.findMany({ where });
```

_Sources: PR #5615, PR #6659, PR #4757_

### Type Safety in Storage and Serialization

- Store values that need numeric comparison in typed columns (numeric, bigint, date) — lexicographic ordering silently produces wrong results for numbers
- Never convert BigInt to Number for serialization — precision loss is silent; use string representation over the wire
- When a value exists in multiple typed columns (string, integer, date), check the most specific type first — a string fallback shadows all other branches

```ts
// Bad — silent precision loss
JSON.stringify({ amount: Number(bigIntValue) });

// Good — use replacer
JSON.stringify(data, (_, v) => typeof v === "bigint" ? v.toString() : v);
```

_Sources: PR #4855, PR #4056, PR #3860_

### Explicit Field Handling in ORM Operations

- Never spread input objects into Prisma create/update calls — duck typing can silently null out columns via extra properties
- When modifying create/update operations, verify the `include`/`select` clause still matches the relations being written
- Explicitly destructure and list each field you intend to set

```ts
// Bad — spreading can set unexpected columns to null
await prisma.entity.create({ data: { ...input } });

// Good — explicit fields
const { name, email, orgId } = input;
await prisma.entity.create({ data: { name, email, orgId } });
```

_Sources: PR #5323, PR #4416_

### Soft Delete and Uniqueness

- When enforcing uniqueness (handles, slugs, emails), query across all records including soft-deleted/archived ones
- When implementing archive, always consider the re-activation path — the "add" flow must detect archived records and unarchive them instead of creating duplicates that violate unique constraints
- Never use user-editable display names as identifiers for system records — add a `system` flag or reserved enum

```ts
// Bad — misses archived records
const exists = await prisma.room.findFirst({
  where: { handle, deletedAt: null },
});

// Good — checks all records
const exists = await prisma.room.findFirst({ where: { handle } });
```

_Sources: PR #3992, PR #5062, PR #4490_

### Idempotent Scripts and Flows

- Backfill scripts should filter to unprocessed records (`WHERE column IS NULL`) rather than re-processing everything
- Seeding and onboarding scripts should use upsert or `createMany({ skipDuplicates: true })`
- Design invite/token acceptance flows to be idempotent — users revisit links and the system should handle re-acceptance gracefully

```ts
// Bad — re-processes all records on every run
const all = await prisma.item.findMany();

// Good — only unprocessed
const pending = await prisma.item.findMany({
  where: { sortValue: null },
});
```

_Sources: PR #5731, PR #6541, PR #3342_

### Mutation Transparency

- Mutation functions should fail explicitly on invalid input — never silently modify user data (e.g., appending "-1" to handle collisions)
- Generate derived values (handles, slugs) server-side rather than accepting client-computed versions
- Prefer user-set values over code-defined defaults for display fields — hardcoded mappings should be fallbacks, not overrides
- Avoid hardcoded assumptions about the most common case (e.g., defaulting country to "United States") — showing nothing is better than showing wrong data

_Sources: PR #5062, PR #4630, PR #4314_

### Composite Keys and Identifiers

- When building composite keys from UUIDs, use a separator that cannot appear in the components (`:` not `-`)
- When a system exposes multiple ID formats (UUID vs short ID), all import/lookup flows must accept the public-facing format
- For nullable foreign keys in join tables, a unique constraint on the nullable column alone works — PostgreSQL allows multiple NULLs

```ts
// Bad — ambiguous split since UUIDs contain hyphens
const compositeId = `${entityId}-${roomId}`;

// Good
const compositeId = `${entityId}:${roomId}`;
```

_Sources: PR #4589, PR #3269, PR #6093_

### Server-Side Side Effects

- Side effects that must always accompany an operation (thumbnails after upload, audit logs after mutations) belong in the server-side handler, not client code
- Auth/identity sync that runs on page load must never throw blocking errors for data conflicts — handle gracefully to avoid locking users out
- When reassigning identity links between accounts, log the operation and consider orphaned relationships in related tables
- In mapping/transformation loops, verify the output references the correct iteration variable — not a captured outer variable (especially critical in compliance flows like KYC)

```ts
// Bad — client triggers thumbnail after upload (other paths miss it)
await uploadFile(file);
await generateThumbnail(file); // in React component

// Good — server handles it atomically
async function confirmUpload(fileId: string) {
  await generateThumbnail(fileId);
  await markUploadConfirmed(fileId);
}
```

_Sources: PR #3007, PR #3636, PR #3975, PR #6777_

### Data Format Integrity

- Never apply generic string truncation to structured values (URLs, emails, identifiers) — truncation corrupts them silently
- Normalize inconsistent formats (e.g., color hex with/without `#`) at the read boundary using existing utilities
- Use `\s` for whitespace validation, not just the space character — users introduce tabs and non-breaking spaces
- When fixing a bad pattern (like hardcoded defaults), search the codebase for similar instances

_Sources: PR #2787, PR #3427, PR #4197_

### Cross-Table Constraints

- For cross-table invariants (e.g., FK must reference a row with matching parent org), use DB-level triggers — Postgres CHECK constraints cannot reference other tables
- For business logic enforcement, prefer explicit data layer functions with `SELECT FOR UPDATE` over triggers — triggers hide behavior and make debugging difficult
- Validation logic must respect exclusion/override lists — if the UI hides fields based on exclusions, backend validation must mirror those conditions

_Sources: PR #2802, PR #5037, PR #4999_

### Rails Transaction Safety

- Wrap paired destructive operations (multiple saves, create + update) in a transaction
- Do not use a single transaction when operations touch multiple databases — partial rollback leaves cross-DB state inconsistent
- Keep transactions small: set attributes outside, wrap only `save!` and sync calls inside
- Never rescue exceptions inside a transaction if that operation is the reason for the transaction — it causes commit despite failure
- Don't raise `ActiveRecord::Rollback` for flow control — it silently swallows errors in nested transactions
- Use `ApplicationRecordMinimal.transaction` per project convention
- Before removing apparent indirection in service objects, verify it doesn't exist for transaction scoping — short transactions reduce lock contention on high-traffic tables
- Never use the return value of a Sorbet `void`-typed method to determine success — `VOID` is always truthy and masks failures

```ruby
# Bad — rescue defeats the transaction
ActiveRecord::Base.transaction do
  record.save!
  begin
    ExternalService.sync!(record)
  rescue => e
    # transaction commits despite failure!
  end
end

# Good — let exception propagate for rollback
ApplicationRecordMinimal.transaction do
  record.save!
  ExternalService.sync!(record)
end
```

_Sources: PR #20970, PR #21263, PR #21565, PR #22436, PR #19094, PR #22041, PR #17926, PR #26544, PR #22159_

### External Calls Last in Transactions

- In transactions mixing DB writes with external service calls, place external calls last
- Local/reversible changes should happen first — if they fail, nothing external has changed
- Never trigger external side effects (syncs, webhooks, jobs) inside a transaction — move to after_commit
- Use rescue-and-destroy sparingly; transactions guarantee all-or-nothing behavior more reliably

```ruby
# Bad — external call before local write, inconsistent on rollback
transaction do
  ExternalService.unclose!(member)
  member.destroy!  # if this fails, external state is wrong
end

# Good — local first, external last
transaction do
  member.destroy!
  ExternalService.unclose!(member)
end
```

_Sources: PR #19094, PR #22041, PR #22436, PR #23898, PR #19938_

### Per-Item Transactions in Loops

- Don't wrap an entire loop in a single transaction unless all items must succeed atomically
- If individual items can fail independently, use separate transactions per item
- A single transaction around a loop means one failure rolls back all prior successes

```ruby
# Bad — one failure undoes all prior work
transaction do
  transfers.each { |t| process!(t) }
end

# Good — independent processing
transfers.each do |t|
  transaction { process!(t) }
end
```

_Sources: PR #24245_

### Pessimistic Locking for Find-or-Create

- Use `with_lock` / `SELECT FOR UPDATE` for find-or-create patterns to prevent race conditions
- Bare find-then-create without a lock is vulnerable to duplicate record creation under concurrency
- `create_or_find_by!` is not fully race-safe — it can still raise `RecordNotUnique`; add a rescue with retry
- Don't mock ActiveRecord locking methods in tests — use `create` instead of `build_stubbed`

```ruby
# Bad — race condition creates duplicates
rel = LpRelationship.find_by(syndicate: syndicate)
rel ||= LpRelationship.create!(syndicate: syndicate)

# Good — row-level lock prevents duplicates
syndicate.with_lock do
  LpRelationship.find_or_create_by!(syndicate: syndicate)
end
```

_Sources: PR #21113, PR #22943_

### Lock Cleanup at the Outermost Scope

- Place lock release/cleanup in an `ensure` block at the outermost scope where the lock is acquired
- Nesting cleanup inside conditionals creates paths where locks are never released
- For multi-resource locks, ensure partial acquisitions are fully cleaned up on failure

_Sources: PR #22284_

### Sync Watermark Correctness

- When implementing incremental sync with a watermark timestamp, set it to the latest record's timestamp — not `Time.current`
- Overstating the sync point risks missing records arriving between timestamp capture and data fetch
- The invariant: there are no unknown records before this timestamp

```ruby
# Bad — overstates what's been processed
sync.update!(synced_at: Time.current)

# Good — watermark matches actual data
latest = transfers.max_by(&:created_at)&.created_at || Time.current
sync.update!(synced_at: latest)
```

_Sources: PR #23862_

### Align Side Effects with Domain Semantics

- Don't create external service resources (integrations, subsidiaries) at the point of intent/agreement
- Create them when the concrete entity that needs the resource actually exists
- This avoids orphaned external resources and keeps lifecycle aligned with actual usage

_Sources: PR #20670_

### Cascading Updates for Denormalized References

- When a domain object has denormalized references (entity_id on multiple related records), treat updates as a transactional unit
- A service that updates one field must also update all fields that derive from or depend on it
- Cross-reference with how other parts of the codebase define the same concept to maintain consistency

_Sources: PR #17795, PR #23028_

### Use Hash#fetch for Required Keys

- Use `Hash#fetch` instead of `Hash#dig` when the key is expected to always exist
- `fetch` raises `KeyError` on missing keys, surfacing data integrity issues immediately
- Reserve `.dig` for genuinely optional nested paths
- Use `T.must()` instead of `.present?` when a value should never be nil — assertions surface bugs, nil guards swallow them

```ruby
# Bad — silently returns nil for missing keys
task.dig(:required_field)

# Good — raises on missing key
task.fetch(:required_field)
```

_Sources: PR #23596, PR #17430_

### Never Match Financial Records on Amount Alone

- Amounts are not unique identifiers — use structural foreign keys (campaign ID, entity ID)
- Account for partial payments where multiple records correspond to a single logical transaction
- When filtering financial records by date, use a fallback chain of date fields to avoid silently dropping records

_Sources: PR #19293, PR #17908_

### Make Impossible States Structurally Impossible

- Prefer model validations, DB constraints, or workflow guards over defensive runtime code for "impossible" edge cases
- Defensive handling of impossible states masks data integrity issues and gives false confidence
- Validate pre-transition state matches expectations before running validations that depend on it
- When a service operates on records in a specific state, assert the count matches expectations and raise on unexpected multiplicity — especially in financial domains

```ruby
# Bad — silently processes however many exist
incomplete_payments.each { |p| adjust!(p) }

# Good — assert invariant before processing
raise DataIntegrityError, "Expected 1 incomplete payment, found #{incomplete_payments.count}" if incomplete_payments.count != 1
adjust!(incomplete_payments.first)
```

_Sources: PR #23776, PR #22680, PR #22635_

### Reports Must Derive from Source Logic

- When building reporting or export features that explain system-computed values, derive from the same source logic as the core computation
- Duplicating or reimplementing calculation logic in a report creates drift and erodes trust in the output
- Cross-reference existing services (e.g., capital account upsert, allocation models) rather than recomputing from raw data

_Sources: PR #19136_
