---
scope: all
---

# Performance

### Push Filtering Into the Database

- Always filter in the DB WHERE clause, not in application code after fetch
- Select only the columns you need — avoid fetching full records when a subset suffices
- Use Prisma `include`/`where` clauses to push conditions into the query layer

```typescript
// Bad — fetches all invites, filters in memory
const invites = await db.portalInvite.findMany({ where: { orgId } });
const pending = invites.filter(i => i.redeemedAt === null);

// Good — filters at the DB level
const pending = await db.portalInvite.findMany({
  where: { orgId, redeemedAt: null },
  select: { id: true, email: true },
});
```

_Sources: PR #6889, PR #2686, PR #4098, PR #4848, PR #3705_

### Batch Database Operations

- Replace per-item DB queries in loops with batch operations (`findMany`, `groupBy`, `deleteMany`)
- Before copying a per-item query pattern, check if the original's constraints apply — pure DB queries can use WHERE IN
- Use Prisma's array-style `$transaction([...])` for bulk writes — it uses one connection and skips round-trips

```typescript
// Bad — O(n) round-trips
for (const id of tagIds) {
  const count = await db.tagRelation.count({ where: { tagId: id } });
  if (count === 0) await db.tag.delete({ where: { id } });
}

// Good — constant round-trips
const counts = await db.tagRelation.groupBy({ by: ['tagId'], where: { tagId: { in: tagIds } } });
const orphanIds = tagIds.filter(id => !counts.find(c => c.tagId === id));
await db.tag.deleteMany({ where: { id: { in: orphanIds } } });
```

_Sources: PR #5553, PR #2666, PR #3489, PR #2655_

### Don't Over-Batch Bulk Operations

- Don't manually batch `updateMany`/`createMany` calls — PostgreSQL supports up to 65k parameters per statement
- A single bulk operation is faster and safer than multiple batched calls that hold a transaction open longer

```typescript
// Bad — unnecessary batching adds 25 round-trips
for (const chunk of chunks(ids, 200)) {
  await prisma.$transaction([prisma.record.updateMany({ where: { id: { in: chunk } }, data })]);
}

// Good — single call handles 5000 IDs fine
await prisma.record.updateMany({ where: { id: { in: ids } }, data });
```

_Sources: PR #4003_

### Parallelize Independent Async Operations

- Use `Promise.all` for independent async lookups in resolvers and handlers
- For conditional parallel work, use the spread-conditional pattern inside `Promise.all`

```typescript
// Bad — sequential when operations are independent
const account = await getFinancialAccount(entityId);
const mmf = await getMoneyMarketFund(entityId);

// Good
const [account, mmf] = await Promise.all([
  getFinancialAccount(entityId),
  getMoneyMarketFund(entityId),
  ...(needsAudit ? [createAuditLog(entityId)] : []),
]);
```

_Sources: PR #5834, PR #4058_

### Cap Database Concurrency

- Never use unbounded `Promise.all` for database operations — it exhausts the connection pool
- Use bounded concurrency (`promiseUtils.map` with a cap) or serial execution for batch DB work
- For backfills/migrations, prefer serial execution or wrap in a transaction for single-connection use
- When small queries don't need parallelism, serial is simpler with negligible latency cost

```typescript
// Bad — unbounded parallelism
await Promise.all(groupByValues.map(v => db.aggregate({ where: { group: v } })));

// Good — bounded concurrency
await promiseUtils.map(groupByValues, v => db.aggregate({ where: { group: v } }), { concurrency: 4 });
```

_Sources: PR #5696, PR #4116, PR #4782_

### Design Compound Indexes for Query Patterns

- Remember the leftmost prefix rule: only queries filtering on leading column(s) can use a compound index
- If you need to query a non-leading column independently, add a separate index
- Don't create single-column indexes when a composite index already covers your query patterns
- Column order: equality columns first, then range columns; within groups, highest cardinality first

```prisma
// Redundant — if queries always filter by (orgId, accountId)
@@index([organizationId])           // covered by composite below
@@unique([organizationId, accountId])

// Good — only the composite
@@unique([organizationId, accountId])
// Add @@index([accountId]) only if you query by accountId alone
```

_Sources: PR #3937, PR #2768, PR #22255_

### Eager-Load Associations

- Fetch related data in the initial query's `include` rather than making follow-up DB trips
- Pair composed data-fetching functions with dataloaders to avoid N+1 in list resolvers
- Use `satisfies` with `GetPayload` to derive type-safe results from include definitions

```typescript
// Bad — extra round-trip
const file = await db.dataRoomFile.create({ data });
const withStates = await db.dataRoomFile.findUnique({ where: { id: file.id }, include: { states: true } });

// Good — include in the original query
const file = await db.dataRoomFile.create({ data, include: { states: true } });
```

_Sources: PR #2655, PR #6275_

### Diff Before Redundant Writes

- When syncing or upserting records that trigger side effects (audit logs, append-only chains), add a diff check
- Skip writes when the new state is identical to the current state
- This prevents unbounded growth in append-only structures and reduces unnecessary DB load

_Sources: PR #4293_

### Instrument Expensive Hot Paths

- When adding expensive operations to frequently-called code paths, add logging to monitor real-world frequency
- Don't pre-optimize for rare edge cases with extra queries — log and monitor first
- Start cron jobs and scheduled tasks with conservative intervals; tighten based on observed data

_Sources: PR #3922, PR #4064, PR #5314_

### Size Timeouts and Resources to Production Data

- Query production data to understand realistic upper bounds before setting timeouts
- Document expected cardinality and scaling assumptions on array-accepting interfaces
- Right-size CI memory allocations for the workload — don't copy from heavier services

_Sources: PR #4294, PR #4500, PR #3323_

### Virtualize Large Tables

- Use row virtualization from the start when rendering tables with hundreds+ rows
- Check if the design system provides a virtualized table variant before building with a naive list
- Retrofitting virtualization later is harder than starting with it

_Sources: PR #6216_

### Throttle Scroll and Resize Handlers

- Never attach expensive handlers directly to raw scroll/resize events
- Use `requestAnimationFrame()` or a throttle utility to limit execution frequency
- Check for existing scroll utilities (e.g., `scrollSpy` in `lib/scroll`) before writing new ones

_Sources: PR #4374_

### Avoid Layout-Level Data Refetching

- Don't place data-fetching hooks in layout components that re-render on every navigation
- Nav/sidebar data that rarely changes should be fetched once and cached, or placed in a layout segment that doesn't unmount on route changes

_Sources: PR #5161_

### Avoid Committing Large Binary Assets

- Don't commit large PNGs or binaries to git — they inflate clone size permanently
- Use compressed formats (webp) and consider hosting large assets externally (CDN/S3)

_Sources: PR #4417_

### Pre-Index for O(1) Lookups in Loops

- When looking up records by ID inside a loop, pre-index them into a hash rather than scanning with `find` each iteration
- This converts O(n*m) to O(n+m)

```ruby
# Bad — O(n*m) scanning
closings.each { |c| members.find { |m| m.id == c.member_id } }

# Good — O(1) lookup
members_by_id = members.index_by(&:id)
closings.each { |c| members_by_id[c.member_id] }
```

_Sources: PR #18220_

### Hoist Loop-Invariant Computations

- Move computations that don't change between iterations outside the loop
- Hoist global condition checks and apply them once with `select!` after collecting results

```ruby
# Bad — recomputed every iteration
documents.each do |doc|
  shared_value = compute_expensive_thing
  process(doc, shared_value)
end

# Good — computed once
shared_value = compute_expensive_thing
documents.each { |doc| process(doc, shared_value) }
```

_Sources: PR #21015, PR #22272_

### Use INNER JOIN When Rows Are Required

- When you require the joined table's rows to exist (filtering out NULLs), use INNER JOIN instead of LEFT JOIN
- A LEFT JOIN followed by a presence check is a code smell — it forces the DB to process all rows before discarding NULLs

_Sources: PR #22215_

### Diagnose Query Plans Before Restructuring Code

- When a query is slow, check whether the database optimizer is choosing a bad plan before restructuring code
- Optimizer hints (e.g., MySQL `USE INDEX`) can fix the root cause without breaking DRY
- Duplicating business logic to work around DB performance hides the real problem

_Sources: PR #22254_

### Co-locate Batch Methods with Single-Record Methods

- When adding a batch/bulk version of an existing service method, co-locate it in the canonical service class
- Have the single-record version delegate to the batch version so logic stays DRY

```ruby
# Bad — batch logic duplicated in consuming service
class ConsumingService
  def batch_advisor_is_angellist(ids) ... end
end

# Good — co-located, single delegates to batch
class AdvisorsService
  def batch_advisor_is_angellist(ids) ... end
  def advisor_is_angellist?(id)
    batch_advisor_is_angellist([id]).first
  end
end
```

_Sources: PR #22593_

### Validate All Before Executing Side Effects

- When processing a batch that involves both validation and side effects (uploads, writes), validate all items first
- This prevents partial completion where some items are persisted but the operation ultimately fails

_Sources: PR #24584_

### Elasticsearch Index Versioning

- When changing Elasticsearch analyzer settings, create a new index version — analyzers cannot be changed on existing indices
- Deployment sequence: deploy new version with sync, reindex, switch reads, clean up old version

_Sources: PR #24291_

### Reindexing Triggers for Derived Search Data

- When adding derived data to a search index from associated records, ensure there is a reindexing trigger for every data source
- Use `touch` or callbacks to propagate changes when associated records change independently of the indexed model

_Sources: PR #25190_

### Never Fetch Assets from Source Control at Runtime

- Don't fetch assets, scripts, or files from GitHub (or any external repo) at runtime in APIs or lambdas
- Bundle assets in the container image build or serve them from a CDN with proper cache headers
- Runtime fetches from source control bypass versioning guarantees, create unbounded latency and cost, and couple deployments to external service availability

_Sources: PR #2193_
