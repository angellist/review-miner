---
scope: backend
---

# Migration Safety

### Avoid Postgres Enums for Mutable Value Sets

- Use string columns with application-layer validation instead of DB enums when values may change
- DB enums require schema migrations to add or remove values — expensive and risky
- Reserve DB enums only for truly stable, well-established value sets

```ruby
# Bad — DB enum locks you into a migration for every new status
create_enum :transfer_status, ["pending", "complete"]

# Good — string column + code-level validation
# In Prisma: type String, enforce via zod/TypeScript union
validates :transfer_status, inclusion: { in: VALID_STATUSES }
```

_Sources: PR #6938, PR #3573_

### Design onDelete Strategy at Schema Time

- Decide CASCADE, SET NULL, or RESTRICT for every foreign key when creating the relation
- Cascade for tightly coupled children that have no meaning without the parent
- SET NULL for loosely coupled references
- Leaving default RESTRICT without intentional design causes runtime constraint errors

```prisma
// Good — explicit cascade for child records
model DataRoomSection {
  dataRoom   DataRoom @relation(fields: [dataRoomId], references: [id], onDelete: Cascade)
  dataRoomId String
}
```

_Sources: PR #6938, PR #3299_

### Delete Dependents Before Parents

- Process dependent records (migrate, merge, or delete) before deleting the parent
- Foreign key constraint errors often only surface in production with real data
- Operation ordering matters for referential integrity — test with realistic data

```typescript
// Bad — deletes parent while children still reference it
await prisma.entity.delete({ where: { id: entityId } });

// Good — merge/migrate dependents first
await prisma.permissionSet.updateMany({ where: { entityId }, data: { entityId: targetId } });
await prisma.entity.delete({ where: { id: entityId } });
```

_Sources: PR #5068, PR #3299_

### Sequence Destructive Schema Changes

- Column renames and drops risk breaking live consumers if migration and app code deploy out of sync
- Evaluate whether a change needs multi-step sequencing (add new → dual-write → backfill → read new → drop old)
- If deploying without sequencing, confirm off-peak deployment explicitly — don't assume

_Sources: PR #3662_

### Backfill Scripts: Isolate Transaction Boundaries

- Don't wrap an entire bulk backfill in a single transaction — one failure rolls back everything
- Batch into smaller independent transactions so failures are isolated and recoverable
- Use a separate connection pool for migration scripts to avoid starving the production app

_Sources: PR #3531_

### Do JSONB Transforms in Application Code

- For one-off migrations that transform JSONB data, parse and manipulate in application code, not raw SQL
- Complex `jsonb_set`/`jsonb_agg`/`jsonb_delete` chains are hard to reason about and test
- Application-level transforms are easier to roll back if unintended writes occur

_Sources: PR #3540_

### JSON Columns Need Application-Layer Schema Validation

- JSON/JSONB columns are appropriate for polymorphic event metadata with per-type shapes
- Pair them with application-layer schema validation (e.g., zod) to enforce structure
- Still use explicit columns for relational foreign keys and frequently queried fields

_Sources: PR #6050_

### Choose Column Types That Match Semantic Intent

- Use `text[]` for simple string arrays; reserve JSONB for complex nested structures
- Use `date` columns for values that don't need time-of-day precision — `datetime` adds timezone complexity when only the calendar date matters
- Regardless of storage choice, ensure the GraphQL schema accurately represents the data type

_Sources: PR #3681, PR #19989_

### Prefer Framework Migrations Over Ad-Hoc Scripts

- For simple data changes, use Prisma migrations instead of one-off scripts
- Migrations run automatically during deployment, apply in dev when pulling, and are idempotent

_Sources: PR #3236_

### Document Constraints Prisma Cannot Represent

- When adding check constraints, triggers, or partial indexes via raw SQL, comment them in the Prisma schema
- These constraints are invisible to developers reading application code
- Undocumented constraints cause confusing runtime validation errors

```prisma
/// CHECK constraint: at least one of (docCount, folderCount) must be set
/// See: migration 20240301_add_count_check.sql
model DataRoomSection {
  docCount    Int?
  folderCount Int?
}
```

_Sources: PR #6994, PR #3530_

### Consistent Prisma @map Directives

- If your convention maps camelCase fields to snake_case columns, apply `@map` uniformly across all fields
- Inconsistent mapping creates confusion about actual column names in the database

_Sources: PR #5398_

### Prisma Naming Conventions

- Relation fields: use plural form, prefix with parent model name (e.g., `entityBankAccounts`)
- Use `View` suffix for relations that reference database views, not tables
- Use triple-slash (`///`) comments so docs propagate to generated client code and IDE tooltips
- Choose relationship names that read naturally (e.g., `dataRoom.forVehicles`)

_Sources: PR #5398, PR #5646, PR #3447_

### Mark Temporary Fields and Minimize Consumers

- When adding fields you know will change, leave explicit comments marking them as temporary
- Document the intended final shape so future developers know the migration plan
- Minimize consumers of temporary APIs to reduce migration burden
- Place data on the model that conceptually owns it, even if another location is more convenient

_Sources: PR #5401, PR #4463_

### Name Fields for What They Are, Not What They Might Become

- Use specific field names tied to the current domain (e.g., `treasuryCustomerAccountId`) rather than generic names (e.g., `id`)
- Premature abstraction in data models creates confusion and is harder to reverse than adding abstraction later
- Verify which relationships are current vs. paused/deprecated when models are mid-migration
- Prefix cross-subsystem foreign keys with the subsystem name (e.g., `cptr_subadvisor_id` not `subadvisor_id`)

_Sources: PR #5398, PR #4463, PR #19466_

### Separate Migrations into Their Own PRs

- Keep database migrations in separate PRs from the application code that depends on them
- Migrations run before code deploys — bundling them risks referencing columns/tables that don't exist yet
- Destructive migrations (dropping tables/columns) must be in a follow-up PR after the code that removes references
- Independent PRs allow independent rollback and simpler review

_Sources: PR #17607, PR #19191, PR #20356, PR #23668, PR #24883, PR #25118, PR #26024, PR #26115, PR #23862_

### Three-Step Column Drop in Rails

- Add `self.ignored_columns` to the model and deploy
- Deploy the migration that drops the column
- Remove the `ignored_columns` entry in a follow-up PR
- The `ignored_columns` entry prevents ActiveRecord from reading the column mid-deploy

```ruby
# Step 1 — deploy first
class Fund < ApplicationRecord
  self.ignored_columns += ["legacy_status"]
end

# Step 2 — deploy migration after step 1 is live
remove_column :funds, :legacy_status

# Step 3 — remove ignored_columns entry after migration runs
```

_Sources: PR #21359_

### Multi-Step Field Rename and Deprecation

- Renaming a persisted attribute in one step breaks existing records on load
- Follow add new → backfill → remove old across separate PRs
- Audit all related methods during parameter renames — remove deprecated methods entirely rather than updating them
- For cross-service field migrations, make both old and new fields nilable with an at-least-one validation during transition
- Document the phased plan in the PR description so reviewers can verify the full path

```ruby
# Bad — one-step rename breaks existing records
rename_column :funds, :old_name, :new_name

# Good — phased: add new, backfill, then drop old
add_column :funds, :new_name, :string
# backfill script: Fund.update_all("new_name = old_name")
# follow-up PR: remove_column :funds, :old_name
```

_Sources: PR #21434, PR #24898, PR #17715, PR #24267, PR #20065_

### Fail Fast on Unresolvable IDs During Migrations

- During ID or entity migrations, raise on unresolvable old IDs instead of silently accepting nil
- Users with stale frontends during deploys will submit old-format IDs — silent nil is data corruption
- A visible error that prompts a page reload is far better than silent data loss

_Sources: PR #20505_

### Clean Up Post-Migration Defensive Code

- After a backfill completes, remove the defensive code paths that handled the pre-migration state
- Vestigial null coalescing, fallback logic, and verification branches add complexity and confuse future readers
- Once a validation prevents an invalid state, remove runtime cleanup code that handled it — use one-time scripts for existing bad data
- Treat backfill completion as a trigger to audit and remove associated workarounds

_Sources: PR #21070, PR #22951_

### Don't Propagate Migration-Era Workarounds

- Temporary escape hatches (e.g., `checked(:never)`, `_command` naming) must not be copied into new code
- When encountering them, remove them rather than carrying them forward
- New code should always use the target technology and patterns, not the legacy ones
- Adding new files in a legacy format (e.g., HAML when migrating to React) increases migration debt
- When a newer version of a service or index exists alongside a deprecated one, always target the new version for changes — feature work added to the deprecated version may never reach production if the migration completes first
- Don't carry forward hardcoded entity IDs from legacy code — handle edge cases via data backfills or configuration so the new module stays clean

_Sources: PR #22191, PR #19211, PR #19857, PR #23830, PR #22547, PR #24481, PR #22770_

### Guard Destructive Operations with Exclusion Criteria

- Destructive batch operations need explicit guards for records that should never be affected
- Don't rely on operators to know which records are safe — encode invariants in the service itself
- Cross-reference recent incident fixes before writing deletion logic to avoid reintroducing conditions those fixes prevent
- Service methods should validate preconditions internally, not rely on callers to filter correctly

```ruby
# Bad — trusts caller to filter
def reverse_migration(fund)
  fund.commands_data.destroy_all
end

# Good — self-contained safety
def reverse_migration(fund)
  raise "Cannot revert native commands fund" if fund.started_on_commands?
  raise "Legacy GL entries exist" if fund.legacy_gl_entries.any?
  fund.commands_data.destroy_all
end
```

_Sources: PR #22679, PR #25349_

### Backfill Before Adding Model Validations

- Adding validations to existing tables retroactively makes all non-conforming records invalid
- Any subsequent save/update on those records will fail unexpectedly
- Plan and execute data backfill before or alongside the validation migration
- For boolean columns on large tables, use a two-step approach: add column with default, then backfill and add NOT NULL constraint

_Sources: PR #24518, PR #20565_

### Migrations Must Not Reference App Models

- App models can change in future PRs, altering the migration's meaning after the fact
- Define a plain `ActiveRecord::Base` subclass with an explicit `self.table_name` instead
- Avoid adding migrations to production that only solve local development problems

```ruby
# Bad — app model may change later
class AddCleanup < ActiveRecord::Migration[7.0]
  def up
    Fund.where(legacy: true).delete_all
  end
end

# Good — standalone class decoupled from app
class AddCleanup < ActiveRecord::Migration[7.0]
  class Fund < ActiveRecord::Base
    self.table_name = "funds"
  end
  def up
    Fund.where(legacy: true).delete_all
  end
end
```

_Sources: PR #17786_

### Large Table Migration Safety

- When a migration touches multiple tables and at least one is large, split into per-table migrations or disable transaction mode
- For large, frequently-written tables, use `algorithm: :instant` and test locally with strong_migrations
- Batch multiple column changes on the same table into a single `change_table` block to reduce ALTER TABLE operations and lock time
- Wrap destructive operations (drop table/column) in `safety_assured` to acknowledge risk explicitly

_Sources: PR #20565, PR #22485, PR #23910, PR #25278_

### Verify Data Parity Before Switching Reads

- When migrating a data source, validate data quality and parity before swapping reads to the new source
- Switching reads with unresolved discrepancies can silently return wrong or nil values
- When migrating SQL to ActiveRecord, compare record counts and field values between old and new implementations on production data
- Watch for date/time semantics: SQL `CURDATE()` returns date-only, Ruby `X.days.ago` returns datetime
- When migrating logic with AI-generated code, carefully verify conditional logic against the original — LLMs can silently invert or simplify boolean conditions in ways that change behavior

```ruby
# Bad — CURDATE() returns midnight, .ago returns current time offset
where("created_at >= ?", 14.days.ago)

# Good — matches SQL date-only semantics
where("created_at >= ?", Date.current - 14.days)
```

_Sources: PR #18892, PR #24000, PR #24964_

### One-Time Script Lifecycle

- Reserve rake tasks for scheduled, recurring jobs — use service objects callable from console for one-time operations
- Check in backfill scripts for auditability, execute them, then remove in a follow-up PR
- Keep backfill concerns out of the domain model's public API — isolate them in dedicated scripts
- Don't leave one-time scripts in the codebase after they've served their purpose
- Preserve single-record entry points used by backfill workflows — consolidating into batch-only methods breaks selective processing

_Sources: PR #20284, PR #21824, PR #24883, PR #25349, PR #17648, PR #24182_

### Scope Bulk Migration Filters Narrowly

- Verify migration filters are narrow enough — "all X for Y" when it should be "all X of type Z for Y" silently corrupts unrelated records
- When processing financial records in bulk, always enforce deterministic ordering by transaction date
- Use `index_by` (not `group_by`) when building lookup hashes where each key maps to exactly one record
- Only clear state for specific steps being re-executed — blanket resets invalidate completed milestones

_Sources: PR #23596, PR #22237, PR #22347, PR #19785_

### Stage-Aware Error Handling in Multi-Stage Migrations

- Explicitly design error handling for each migration stage
- Shadow-write stages should rescue and log errors to avoid production impact
- Final cutover stages must raise to enforce correctness
- Document which stage the code is in so reviewers understand the error handling rationale

_Sources: PR #24267_

### Handle In-Flight Records When Changing Behavior

- When removing an automatic process or changing trigger conditions, check for records created under the old behavior
- Query production data to quantify the gap before merging
- Have a migration or manual remediation plan for stuck records
- When modifying fields that participate in uniqueness/deduplication keys, backfill existing records before the sync runs

_Sources: PR #19546, PR #23086_

### Avoid Nullable Booleans in Rails

- Rails `?` predicate treats `nil` as `false`, silently hiding the "unknown" state
- If nullable booleans are needed as an interim migration strategy: require the value for new records immediately, avoid the `?` predicate during the interim, and backfill + add NOT NULL as a follow-up
- Don't overload `nil` vs empty collection to represent different business states — use explicit parameters

```ruby
# Bad — nil hides "we don't know" state
fund.has_net_exercise? # nil treated as false

# Good — explicit interim handling
validates :has_net_exercise, inclusion: [true, false], on: :create
# Avoid .has_net_exercise? until backfill complete
```

_Sources: PR #26372, PR #26312_

### Create New Models in the Target Database

- When actively migrating between databases (e.g., MySQL to PostgreSQL), always create new models in the target DB
- Creating them in the legacy DB adds to migration burden and forces workarounds like `disable_joins`
- Similarly, prefer Rails `dependent: :destroy` over database-level ON DELETE CASCADE for visibility in the application layer

_Sources: PR #23814, PR #19932_

### Comment Temporary and Time-Gated Migration Logic

- When adding time-gated logic (date-based conditionals for transitions), add a TODO stating when it can be removed
- Exceptional logic for one-time transitions needs a comment explaining why it exists, what it handles, and its removal criteria
- Without this, temporary transition code lives forever because no one remembers it was meant to be temporary

_Sources: PR #24096, PR #23901_

### Add Indexes Before Deploying Queries That Need Them

- When introducing queries that sort or filter on a column in a frequently-loaded page, verify the column is indexed
- Ship the index migration in a separate PR before the feature PR to ensure it's deployed first
- Only add indexes that match actual query patterns — a standalone index on a column only queried as part of a composite key wastes writes

_Sources: PR #17167, PR #26652_

### Verify change_column_null Argument Direction

- `change_column_null(table, column, null)` takes `true` to mean "allow null" — the opposite of what "set non-null" suggests
- Always double-check the argument against Rails docs and model annotations before running in production
- Verify the resulting nullability matches your intent after migration runs

```ruby
# Confusing — does this allow or disallow null?
change_column_null :funds, :status, false  # false = disallow null (NOT NULL)
change_column_null :funds, :status, true   # true  = allow null (nullable)
```

_Sources: PR #21422_

### Distinguish Retroactive from Point-in-Time Data

- Before applying date filters to temporal data, ask: "Is this a point-in-time fact, or a correction that applies retroactively?"
- Entity merges, reclassifications, and similar corrections apply to all historical periods — date-based filtering on them produces incorrect results
- Only filter by `created_at` or `as_of` on records that represent point-in-time snapshots, not retroactive corrections

_Sources: PR #17236_

### Guard Untested Assumptions with Explicit Validations

- Don't rely on "we haven't seen it yet" as justification for skipping edge case handling
- Add validations or guards for unsupported cases so the system fails loudly rather than producing silently incorrect results
- When a method depends on prior data existing, assert that precondition explicitly rather than falling through to a degraded path

```ruby
# Bad — assumes partial exercises never happen because data says so today
def backfill_exercise(warrant)
  position = warrant.exercise_positions.sole
end

# Good — guard the assumption
def backfill_exercise(warrant)
  raise "Partial exercises not supported" if warrant.exercise_positions.count > 1
  position = warrant.exercise_positions.sole
end
```

_Sources: PR #23298, PR #17772_

### Use Domain-Specific Dates for Migration Cutoffs

- When filtering records by "before/after a migration or feature launch," prefer domain-specific date fields over `created_at`
- `created_at` reflects when the row was inserted, which may include backfilled or invalid records that predate the correct implementation
- Use fields like `initiated_on` or `effective_date` that carry business meaning for the cutoff

_Sources: PR #19069_

### Centralize Library Calls to Ease Future Migration

- Wrap third-party library calls in centralized utility functions to create a single migration point when replacing the library
- When introducing a new library that overlaps with an existing one, present a concrete migration plan scoped to a manageable area
- Don't add competing dependencies without team alignment on deprecating the old one

```typescript
// Bad — moment calls scattered across codebase
moment(date).format("MM/DD/YYYY")

// Good — centralized, single point to migrate
formatDate(date, "MM/DD/YYYY")
```

_Sources: PR #25294, PR #23455_

### Optimize Temporal Backfill Workflows

- For one-off Temporal backfill workflows, prefer upfront ID fetching when the payload fits within limits (~2MB) — this guarantees idempotency and prevents newly-created records from slipping into the backfill
- Use cursor-based pagination only when the dataset exceeds payload limits
- Optimize batch sizes to minimize activity count — worker allocation overhead per activity is often the bottleneck, so fewer larger batches outperform many small ones

_Sources: PR #26455_

### Sync Local Schema Before Submitting PRs

- Before switching branches or submitting a PR, ensure your local DB schema matches the target branch
- Roll back any local-only migrations, then run `rails db:schema:dump` to regenerate the schema file from the current DB state
- Stale schema files (e.g., `cptr_schema.rb`) create noisy diffs and can accidentally include unintended schema changes that are hard to notice in review
- Review your full diff before submitting — auto-generated files (schema.json, schema.rb) touched incidentally create merge conflicts and can introduce unintended schema changes

```bash
# Roll back local-only migrations, then regenerate
rails db:rollback STEP=N
rails db:schema:dump
```

_Sources: PR #25396, PR #20198_

### Elasticsearch Index Version Migration

- Follow a strict 4-step sequence when upgrading Elasticsearch index versions to avoid missing or stale search results
- Never switch reads before reindexing is complete — search results will be missing or stale
- Clean up old version sync only after reads have switched, not before

```
# Required deployment order:
# 1. Deploy sync step for the new index version
# 2. Reindex data into the new version
# 3. Deploy the read switch from old to new version
# 4. Remove old version's synchronization code
```

_Sources: PR #24331_
