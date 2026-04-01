---
scope: all
---

# Code Organization

### Consolidate Utilities Into Shared Modules

- Before creating a new utility file, check if a shared module already covers the domain (e.g., `lib/money`, `lib/dates`, `lib/string`)
- Add new helpers as exports in the existing module rather than creating standalone files
- Extend a shared helper with missing functionality rather than reimplementing locally
- Rule of three: when the same logic appears in three places, extract it into a shared utility

```typescript
// Bad — standalone file duplicating existing module
// app/lib/investmentAmount.ts
export function formatAmount(cents: number) { ... }

// Good — add to existing shared module
// lib/money/index.ts
export function formatInvestmentAmount(cents: number) { ... }
```

_Sources: PR #2699, PR #3585, PR #3903, PR #3678, PR #3805, PR #3822, PR #4063, PR #4205, PR #4269, PR #4622, PR #4623, PR #2762, PR #4449, PR #2796_

### Avoid Generic Catch-All Files

- Do not create `helpers.ts`, `config.ts`, or `utils.ts` in component directories — they become junk drawers
- Use semantically named files: `filters.ts`, `types.ts`, `formatters.ts`
- For shared types that prevent circular deps, use a `types.ts` file with only type definitions
- Name lib files after their domain scope, not the product umbrella — `meridian.ts` not `capital.ts`

```
# Bad
components/DataRoom/helpers.ts   ← accumulates unrelated code
lib/capital.ts                   ← too broad, attracts everything

# Good
components/DataRoom/types.ts     ← only shared type definitions
components/DataRoom/filters.ts   ← descriptive of contents
lib/meridian.ts                  ← scoped to actual domain
```

_Sources: PR #3805, PR #3824, PR #4205_

### Group Related Files by Resource

- Group CRUD handlers for the same resource into a resource-named directory
- Follow established conventions — if the codebase uses `lib/` for business logic, keep new code there
- Place shared types/utilities in general-purpose locations (e.g., `models/shared`), not feature-specific directories

```
# Bad — flat files scattered in a shared directory
admin/getOpportunity.ts
admin/createOpportunity.ts
admin/editOpportunity.ts

# Good — grouped by resource
admin/opportunity/get.ts
admin/opportunity/create.ts
admin/opportunity/edit.ts
```

_Sources: PR #3822, PR #3801, PR #4246_

### One Component Per File

- Define one exported React component per file — extract secondary components into their own files
- Place reusable components in a shared location from the start, not buried in a view-specific directory
- Split large router files into one file per endpoint with helpers extracted separately

```typescript
// Bad — multiple exported components in one file
// TransactionPage.tsx
export function TransactionPage() { ... }
export function TransactionSummary() { ... }

// Good — separate files
// TransactionPage.tsx
export function TransactionPage() { ... }
// TransactionSummary.tsx
export function TransactionSummary() { ... }
```

_Sources: PR #3539, PR #3585, PR #4026_

### Keep Integration Modules Single-Purpose

- Scope each integration module to one external service — do not mix concerns
- When adding infrastructure utilities (loggers, throttlers) for a new subsystem, check for existing shared packages first
- Consolidate into shared packages rather than creating parallel implementations

```typescript
// Bad — Datadog tracing inside PostHog module
// integrations/posthog.ts
import { trace } from 'dd-trace';

// Good — separate integration modules
// integrations/posthog.ts  ← PostHog only
// integrations/datadog.ts  ← Datadog only
```

_Sources: PR #3936, PR #4623_

### Avoid Circular Dependencies When Extracting

- When splitting a large file, check that the new file does not import from the original
- If shared types cause circular deps, move them to a dedicated `types.ts` file
- Circular imports may work at runtime but make the dependency graph fragile

```typescript
// Bad — extracted file imports from parent
// components/Table/columns.ts
import { TableConfig } from './Table'; // circular!

// Good — shared types in a neutral file
// components/Table/types.ts  ← both Table.tsx and columns.ts import from here
```

_Sources: PR #3678, PR #3805_

### No Dead Code or Premature Additions

- Only include code in a PR that is actively used by that PR — do not ship code "for later"
- Before migrating legacy code, verify it is still actively used with domain owners
- Code generation should only contain dynamic content — static implementations belong in regular files
- When removing a feature, search the whole file (and related files) for associated constants, enums, and config arrays — partial cleanup leaves dead code that misleads future readers
- When refactoring service methods, audit the parameter list for values no longer used in the method body — dead parameters confuse callers
- Before adding a new data section or abstraction, check whether the information can be derived from existing data — consolidating overlapping data sources reduces code complexity and maintenance burden
- When inlining a helper method, immediately delete the original definition — inlining is only complete when the extracted method is gone
- When deleting or moving a function during a refactor, do a cross-file search for all usages before merging — stale references may not surface at compile time if the removal hasn't landed yet
- Remove "just in case" abstractions (enums, constants, layers) when there is no realistic future need — if a reviewer and author agree an abstraction will never expand, deleting it is the right call (YAGNI)

_Sources: PR #2762, PR #4756, PR #4633, PR #17365, PR #22900, PR #25792, PR #23050, PR #26839, PR #7325, PR #1207_

### Split Behavior Variants Instead of Boolean Flags

- Do not use a boolean parameter to fundamentally switch a function's behavior
- Extract shared logic into a base function and create separate named methods for each variant

```ruby
# Bad — boolean switches entire query
def fetch_members(include_removed:)
  if include_removed
    Member.all
  else
    Member.where.not(status: :removed)
  end
end

# Good — separate methods, shared base
def active_members = base_query.where.not(status: :removed)
def all_members    = base_query
```

_Sources: PR #3914_

### Document Temporary Special Cases

- When code has domain-specific special cases intended to be temporary, add comments explaining the context and intended future state
- This prevents logic from becoming opaque and helps future developers know which branches to clean up

_Sources: PR #4007_

### Push Guards Into the Method They Protect

- Defensive guards belong inside the method, not at call sites
- When a method should be a no-op under certain conditions, encode that as an early return within the method
- When multiple methods share a precondition, push the guard into the shared dependency
- This prevents future callers from forgetting the check

```ruby
# Bad — guard duplicated at every call site
log_dimension_change(dc, key, from, to) if from != to

# Good — guard inside the method
def log_dimension_change(dc, key, from, to)
  return if from == to
  # ...
end
```

_Sources: PR #19681, PR #24247, PR #26206_

### Namespace by Primary Domain Object

- Namespace services under the primary domain object being acted upon
- If a service primarily operates on banking transfers, namespace it under `BankingTransfers`, even if the entry point comes from a membership class
- Maintain clean API boundaries between bounded contexts — don't store foreign keys to entities in another context

```ruby
# Bad — nested under parent's namespace
MembershipClasses::BankingTransfers::CreateService

# Good — reflects primary domain
BankingTransfers::CreateService
```

_Sources: PR #23830, PR #26064_

### Return nil for Missing Data, Not Magic Strings

- Service methods should return nil (or raise) for missing data, not hardcoded fallback strings
- Magic string fallbacks create hidden coupling — every caller must know the exact string to check against
- Returning nil makes the absence explicit and lets callers decide their own fallback

```ruby
# Bad — callers must check for magic string
def fund_name
  name.presence || 'Unnamed Fund'
end

# Good — nil signals absence clearly
def fund_name
  name.presence
end
```

_Sources: PR #23393_

### Name Hash Constants to Indicate Structure

- Name hash/dictionary constants to indicate they are lookup tables, not scalar values
- Use `value_by_key` format (e.g., `carry_percent_by_firm`) instead of just `carry_percent`
- For nested hashes, use `value_by_key_by_key` to make the access pattern self-documenting

_Sources: PR #22131_

### Explicit Assertions Over Deferred Crashes

- When refactoring code that implicitly relied on non-nil values, add explicit assertions (T.must, guard clauses) at the point of access
- Moving the crash site downstream makes debugging harder and obscures the real invariant
- Avoid chaining multiple `T.must` assertions — extract to a variable with a single assertion
- Prefer guard clauses over `T.must` for values that could legitimately be nil at runtime

```ruby
# Bad — nil crash deferred to sort/median call
values = records.map { |r| r.started_at }
values.sort  # crashes here if nil, unclear why

# Good — fail at the assumption point
values = records.map { |r| T.must(r.started_at) }
```

_Sources: PR #20248, PR #17552, PR #26101_

### Configure Timeouts on Internal API Clients

- Always set explicit timeouts on internal service-to-service API clients
- Cross-service calls without timeouts cause cascading latency — a slow downstream blocks the caller indefinitely
- Use reasonable defaults (e.g., 3s for calls blocking user-facing queries) to isolate failures

_Sources: PR #20309_

### Self-Contained Code Comments

- Include the actual reasoning in code comments, not just ticket/incident links
- External links rot — the "why" should live next to the code
- When deferring work, create a tracked ticket and reference it in a `TODO` — incident links are not actionable
- Remove or correct comments that describe logic differently from what the code does

_Sources: PR #17213, PR #21528, PR #19132, PR #19772_

### Accept Objects, Not Extracted Fields

- When a service method needs data from an object, accept the object itself and extract internally
- This reduces nil-checks and type casts at every call site
- The method's API is more intuitive when callers don't need to know which field to extract

```ruby
# Bad — every caller extracts and nil-checks
def deal_partnership_carry?(carry_type)
  T.must(carry_type) == 'DealPartnership'
end

# Good — method handles extraction
def deal_partnership_carry?(carry)
  carry.type == 'DealPartnership'
end
```

_Sources: PR #23695, PR #19466_

### Never Add Code to Deprecated Files

- Don't add new constants, types, or utilities to files marked as deprecated
- Find or create the appropriate home — deprecated files should be shrinking, not growing
- When constants are shared across app boundaries, centralize or make duplication intentional and documented

_Sources: PR #26120_

### Use Project Memoization Patterns

- Use the project's established memoization pattern (rose `memoize`) instead of manual `@ivar ||=`
- Manual instance variable patterns are error-prone (nil caching, initialization ordering)
- Call memoized methods directly rather than accessing their backing instance variables

_Sources: PR #26206_

### Defer Expensive Operations Until Needed

- Place guard clauses before expensive operations (API calls, file downloads, DB queries)
- Don't fetch data unconditionally at method top if it's only used in a conditional branch
- Pass already-fetched data as parameters rather than re-fetching in downstream methods
- When an association or method result is used multiple times, extract it to a local variable — avoids redundant DB queries and makes intent clearer

```ruby
# Bad — API call before guard check; association queried twice
data = ExternalService.fetch(id)
return unless feature_enabled?
notify(startup.contact_user) if startup.contact_user

# Good — guard first; association extracted once
return unless feature_enabled?
data = ExternalService.fetch(id)
contact = startup.contact_user
notify(contact) if contact
```

_Sources: PR #23917, PR #18952, PR #17518, PR #21114_

### Directional Variable Names in Financial Code

- In financial domain code with directional concepts (from/to, debit/credit), variable names must make direction explicit
- Ambiguous names like `payments` lead to misinterpretation — use `payments_from_quarter` or `payments_to_quarter`
- When nil carries specific business meaning (e.g., nil entity_id = charity), encapsulate in a named method

_Sources: PR #18175, PR #24677_

### Provision Env Vars Across All Environments

- When introducing new ENV references in code, ensure they are defined in all target environments (staging, production) in the same PR or a coordinated rollout
- Don't rely on k8s secrets persisting after config removal — this creates hidden dependencies that break in new environments
- Reviewers should audit new `ENV[...]` references and confirm the provisioning plan

_Sources: PR #22511, PR #23946_

### Don't Expose Domain Objects Outside API Boundaries

- Provide accessor methods that return only primitive identifiers (IDs, strings) rather than full model objects
- Re-export constants consumers need in the public API class — don't leak internal implementation references
- After merging services into a monolith, convert network calls to direct in-process calls via a public API boundary layer
- When using packwerk, reference cross-pack constants through the pack's public API namespace (e.g., `DIBSApi::Constants::NOC_CODE_C*`) — direct string literals or internal constant references bypass packwerk enforcement and make violations invisible until CI runs

_Sources: PR #18152, PR #18697, PR #18580, PR #7039_

### Replace Magic Numbers With Named Model Methods

- Extract magic number comparisons into named boolean methods on the model
- Domain concepts should be explicit in the API, not scattered as inline checks

```ruby
# Bad — magic number at every call site
hurdles.select { |h| h.applies_at_multiple == 1.0 }

# Good — named method encapsulates domain concept
class Hurdle
  def base_hurdle? = applies_at_multiple == 1.0
end
hurdles.select(&:base_hurdle?)
```

_Sources: PR #23451_

### Standardize Canonical Data Representations

- Pick one canonical representation for domain values and use it consistently throughout the codebase
- Convert only at system boundaries (API layer, database layer)
- Define configuration defaults in exactly one place — duplicated defaults inevitably diverge

```ruby
# Bad — mixed percentage representations
rate_a = 0.05     # 0-1 scale
rate_b = 5        # 0-100 scale

# Good — one canonical form, convert at boundary
rate_a = 0.05     # always 0-1 internally
rate_b = 0.05
display_rate = (rate_a * 100).to_s + "%"  # convert at display
```

_Sources: PR #23800, PR #23050_

### Gate Multi-Subsystem Operations on All Preconditions

- When an operation spans multiple subsystems, check all preconditions before executing any part
- Order operations so the most reversible step runs first
- When acquiring multiple resources (locks, connections), ensure cleanup of partially-acquired resources on failure

```ruby
# Bad — starts treasury merge before checking comptroller
def perform
  treasury_merge!    # hard to unwind
  comptroller_merge! # fails here → partial state
end

# Good — all checks first, reversible step first
def perform
  raise unless can_merge_treasury? && can_merge_comptroller?
  comptroller_merge! # easier to unwind
  treasury_merge!
end
```

_Sources: PR #22915, PR #22284_

### Return Simplest Type From Intermediate Abstractions

- When building intermediate abstractions (sort services, query builders), return the simplest output type callers need
- Don't leak internal representations (e.g., Arel nodes) that force callers to branch on type
- Refactor to richer types only when all callers can consistently consume them

```ruby
# Bad — callers must handle Arel vs string
def sort_expression
  Arel.sql("...") # some callers need .to_sql
end

# Good — return what callers actually use
def sort_expression
  "..." # SQL string, simple for all callers
end
```

_Sources: PR #22232_

### Remove Redundant Operations Already Handled Upstream

- Before adding a defensive check, verify whether the condition is already guarded upstream in the same code path
- Watch for redundant string operations (.strip, .downcase, .to_s) already handled by the caller or framework
- Don't use `.presence` before `&.` on has_one associations — `&.` already handles nil
- Redundant operations mislead future readers into thinking the value needs that transformation at that point

```ruby
# Bad — .presence is redundant before &.
entity.address.presence&.country

# Good — &. handles nil already
entity.address&.country
```

_Sources: PR #19835, PR #23783, PR #24313_

### Fix Lint Violations at the Source

- Fix lint violations at the source rather than suppressing them with inline ignore comments (e.g., `// biome-ignore`)
- If a rule consistently doesn't apply to the codebase, disable it project-wide in the Biome config — don't annotate every instance
- Use suppress comments only as a last resort for legacy code, with an explicit follow-up to address root causes
- Suppress comments accumulate debt and hide real issues from future reviewers
- When `biome-ignore` or non-null assertions cluster at call sites, treat it as a signal the method's type signature doesn't match reality — widen the parameter type and handle the edge case inside the method

```typescript
// Bad — suppressing type mismatch at every call site
// biome-ignore lint/...
processUrl(value!)

// Good — fix the signature; handle nil internally
function processUrl(url: string | null | undefined) {
  const resolved = url ?? defaultUrl;
  ...
}
```

_Sources: PR #46, PR #26959_
