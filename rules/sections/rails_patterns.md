---
scope: backend
---

# Rails Patterns

### Separation of Concerns Across Layers

- Keep transport/protocol handlers thin — validate request, call domain logic, format response
- Library/data-layer functions should not embed presentation or caller-specific serialization logic
- Client/transport layers should return raw response shapes; let callers handle type transformation
- Data-fetching functions accept simple typed parameters; push query-building to call sites

```ts
// Bad – domain logic in protocol handler
// handlers/prophet/sections.ts
export async function handleSections(req) {
  const sections = await prisma.section.findMany(...)
  return sections.filter(s => s.visible).map(formatForUI)
}

// Good – handler delegates to domain module
// handlers/prophet/sections.ts
export async function handleSections(req) {
  return sectionService.getVisibleSections(req.params)
}
```

_Sources: PR #5327, PR #5204, PR #5559, PR #5931_

### Guard Clauses and Early Returns

- Return early for simple/degenerate cases to reduce nesting
- Derive guard conditions from computed data rather than duplicating the source logic
- For self-referential uniqueness checks, extract to a named function with early returns and comments
- Prefer `return unless condition` over wrapping code in conditional blocks
- Always add a blank line after guard statements (`return if`, `return unless`) per RuboCop convention
- Prefer `if x.nil?` over `unless x` for nil guards — it checks nil specifically, not all falsy values
- Extract nilable values into local variables with early-return guards rather than embedding nil checks in complex expressions (`return false if x.nil?`, then use `x` freely below)

```ts
// Bad – guard duplicates filter logic
if (!hasEntityA && !hasEntityB) return { apiKey: undefined }
const filters = [entityA && ..., entityB && ...].filter(Boolean)

// Good – derive guard from computed result
const filters = [entityA && ..., entityB && ...].filter(Boolean)
if (!filters.length) return { apiKey: undefined }
```

_Sources: PR #5204, PR #5927, PR #5739, PR #24636, PR #25119, PR #18172, PR #26101_

### Module and File Structure

- Keep entry point files focused on orchestration; extract implementation concerns to dedicated modules
- Structure service files with exported (public) functions at the top, internal helpers at the bottom
- Add explicit return type declarations on non-trivial exported functions

```ts
// Good – public API at top, helpers at bottom
export async function processTransfer(id: string): TransferResult {
  const data = await fetchTransferData(id)
  return buildResult(data)
}

// --- internal helpers ---
async function fetchTransferData(id: string) { ... }
function buildResult(data: RawData): TransferResult { ... }
```

_Sources: PR #5495, PR #6247_

### Stateful Resource Lifecycle

- Use a factory pattern for stateful resources (consumers, connections) instead of module-level `let` variables
- Colocate setup and teardown — initialization functions should return their own cleanup closures
- Ensure singleton guard flags are scoped outside the function they protect

```ts
// Bad – scattered module-level state
let consumer: Consumer | null = null
export function start() { consumer = new Consumer() }
export function stop() { consumer?.close(); consumer = null }

// Good – factory encapsulates state
function createConsumer() {
  let instance: Consumer | null = null
  return {
    start: () => { instance = new Consumer(); return () => instance?.close() },
    isRunning: () => instance !== null,
  }
}
```

_Sources: PR #5204, PR #6213, PR #5495_

### Atomic Data Operations

- Prefer Prisma `upsert` over manual find-then-create; it compiles to `INSERT ON CONFLICT`
- For timestamp-derived state machines, use optimistic updates with a state-to-conditions map
- Exception: nested object creation within upsert may trigger additional queries

```ts
// Bad – two queries, race condition window
const existing = await prisma.record.findUnique({ where: { key } })
if (!existing) await prisma.record.create({ data: { key, value } })

// Good – single atomic query
await prisma.record.upsert({
  where: { key },
  create: { key, value },
  update: { value },
})
```

_Sources: PR #2666, PR #6102_

### DRY Repeated Logic

- When repeated blocks differ only in a pattern/type pair, extract a small inner helper
- For recursive/nested data validation, use a generic recursive approach over hardcoded schema structure
- Before adding a new filter to an existing function, verify they share concerns — extract if unrelated
- Remove thin wrapper methods when the logic that justified them is eliminated; inline at the call site

```ts
// Bad – repeated blocks for each field type
if (col.match(/phone/)) result.type = 'phone'
if (col.match(/email/)) result.type = 'email'
if (col.match(/name/))  result.type = 'name'

// Good – data-driven
const FIELD_PATTERNS = [['phone', /phone/], ['email', /email/], ['name', /name/]]
const match = FIELD_PATTERNS.find(([, re]) => re.test(col))
if (match) result.type = match[0]
```

_Sources: PR #6244, PR #4197, PR #4189, PR #23242, PR #24695_

### Unnecessary Async

- Don't mark functions `async` when they return a promise directly without awaiting
- Don't mark functions `async` when they perform no asynchronous operations
- Don't `await` a value being directly returned — the caller already gets a Promise

```ts
// Bad – redundant async
async function getUser(id: string) {
  return prisma.user.findUnique({ where: { id } })
}

// Good
function getUser(id: string) {
  return prisma.user.findUnique({ where: { id } })
}
```

_Sources: PR #5934, PR #6150, PR #6247_

### Branch Once for Mutually Exclusive Variants

- When a function handles mutually exclusive input types, branch once at the top level
- Keep each variant's logic self-contained even if it duplicates some shared helpers
- Before adding conditional branches, verify the logic actually differs between cases

```ts
// Bad – scattered checks
function process(subject: AccountSubject | InviteSubject) {
  const id = 'accountId' in subject ? subject.accountId : subject.inviteId
  // ... more scattered checks later ...
}

// Good – branch once
function process(subject: AccountSubject | InviteSubject) {
  if ('accountId' in subject) {
    return processAccount(subject)
  }
  return processInvite(subject)
}
```

_Sources: PR #5968, PR #6201_

### YAGNI for Exports

- Don't add speculative API surface — every export is a maintenance commitment
- Verify newly added constants, types, or utilities are actually imported somewhere before merging
- If there's no concrete use case, leave it out; it can be added later

_Sources: PR #5204, PR #5204_

### Filter in SQL, Not Ruby

- Use ActiveRecord scopes and `where` clauses instead of loading records and filtering with `.select`/`.reject`
- Use `find_by` when you need a single record matching criteria, not load-all-then-find
- Push aggregates (sum, count, max) into SQL with `.joins` and `.sum` instead of iterating in Ruby
- When an AR scope mirrors a Ruby predicate (e.g., `.active` vs `select(&:active?)`), use the scope
- Prefer existing model scopes over manual status filtering — scopes encode domain-wide definitions

```ruby
# Bad – loads all records, filters in Ruby
llc.form1065s.select { |f| f.tax_year == target_year }

# Good – database-side filter
llc.form1065s.find_by(tax_year: target_year)
```

_Sources: PR #17167, PR #18132, PR #22382, PR #23800, PR #25051, PR #22593, PR #18522_

### ActiveRecord Query Composition

- Prefer AR query methods (`.left_joins`, `.where.not`, `.or`) over raw SQL strings
- Use `.select(:id)` instead of `.pluck(:id)` when IDs feed into another query — keeps it as a subquery
- Preserve AR relations as long as possible; avoid `.to_a` in service return values
- Use `.reorder(nil)` to remove default ordering; `.unscoped` removes ALL default scopes including soft-delete
- Don't call `.pluck('table.column')` on in-memory Ruby arrays — use `.map(&:id)` after `.map`/`.flat_map`
- Use `.none` for empty-result cases and `.distinct` instead of `.uniq` to keep operations in SQL

```ruby
# Bad – pluck loads all IDs into memory
Model.where(id: OtherModel.where(active: true).pluck(:id))

# Good – subquery stays in SQL
Model.where(id: OtherModel.where(active: true).select(:id))
```

_Sources: PR #21241, PR #25040, PR #23800, PR #25068, PR #23949, PR #21526, PR #22904, PR #25041, PR #23311_

### includes vs joins vs preload

- Use `joins` for filtering on associations, `preload` for eager-loading after filtering
- `includes` with conditions forces a single heavy JOIN; split into `joins` + `preload` for performance
- `includes` works correctly with `find_in_batches` (loads per batch)
- To preload on already-loaded records, use `ActiveRecord::Associations::Preloader` directly

```ruby
# Bad – includes with condition forces one big JOIN
Campaign.includes(:segment).where(segments: { active: true })

# Good – joins for filter, preload for data
Campaign.joins(:segment).where(segments: { active: true }).preload(:investments)
```

_Sources: PR #22070, PR #24695, PR #22593_

### Preloaded Associations vs Query Methods

- When associations are already preloaded, use Ruby enumerables (`.find`, `.select`) not AR query methods
- AR methods like `.where`, `.find_by` always hit the database, bypassing preloaded cache
- Choose `exists?` vs `present?`/`blank?` based on context: `exists?` for unloaded, `present?` for preloaded

```ruby
# Bad – hits DB even though association is preloaded
user.investments.where(status: :active)

# Good – uses preloaded data
user.investments.select(&:active?)
```

_Sources: PR #25121, PR #22152_

### where.not Semantics

- `.where.not(a: x, b: y)` generates `NOT (a = x AND b = y)`, not `a != x AND b != y`
- To exclude rows matching any condition independently, chain separate `.where.not` calls
- `.where.not(col: value)` also excludes rows where `col` IS NULL

```ruby
# Bad – excludes only rows where BOTH match
Model.where.not(category: 'no_k1s', total_count: 0)

# Good – excludes rows matching either condition
Model.where.not(category: 'no_k1s').where.not(total_count: 0)
```

_Sources: PR #17760, PR #19637_

### Service Object Conventions

- Services should be static (class-method-only); use presenters for controller response formatting
- Default methods to `private` unless part of the intended public API
- When a service exists for a domain operation, always route changes through it — never bypass in controllers
- Keep business logic out of mailers and models; extract to services
- Don't put expensive operations (API calls) on model methods — move to services where cost is visible
- Avoid thin service wrappers that simply delegate to another service; keep one canonical service per operation
- Shared data-fetching services should return the complete dataset; let callers filter explicitly
- Prefer caller-side preloading over internal memoized fetches — makes data dependencies explicit
- Keep generic processor/extraction services agnostic to specific entity types — push domain knowledge to entity-specific services; the processor should only operate on what the domain layer has marked/configured

```ruby
# Bad – bypassing service in controller
campaign.update!(subadvisors: new_list)

# Good – route through service for side effects
FundraisingCampaigns::UpdateService.call(campaign, subadvisors: new_list)
```

_Sources: PR #17334, PR #19522, PR #18839, PR #22827, PR #24516, PR #18348, PR #23674, PR #20305, PR #20924, PR #23467, PR #25518_

### Unpack Params at the Boundary

- Extract params in the webhook handler or controller, then pass typed values to services
- Services should accept simple typed parameters, not raw param hashes
- This decouples services from transport, improves console debuggability and testability

```ruby
# Bad – raw params hash passed to service
SyncService.call(params)

# Good – params unpacked at boundary
mc_id = params[:membership_class_id]
SyncService.call(membership_class_id: mc_id)
```

_Sources: PR #17332, PR #17268_

### Error Handling

- Rescue `StandardError`, never `Exception` (catches signals and fatal errors)
- Don't rescue-log-reraise; let exceptions propagate naturally unless you transform or add context
- Never use catch-all rescues that normalize all errors to one HTTP status — distinguish client from server errors
- Don't use raise/rescue for control flow; it's expensive (stack trace capture)
- Route errors through the error tracker (Sentry/ErrorTracker), not `puts` or `Rails.logger`

```ruby
# Bad – catch-all swallows server errors
rescue => e
  render json: { error: e.message }, status: 400

# Good – specific error handling
rescue WedgeApiError => e
  render json: { error: e.message }, status: e.status
# Let unexpected errors propagate as 500s
```

_Sources: PR #19211, PR #20755, PR #18474, PR #19058, PR #20386, PR #25262_

### Boolean Pitfalls in Ruby

- Never use `.present?`/`.blank?` on booleans — `false.present?` returns `false`, `false.blank?` returns `true`
- Use `.nil?` to check if a boolean was provided
- Understand `blank?` vs `nil?` vs `empty?`: `blank?` catches nil, empty strings, empty arrays, and false
- Avoid `T.nilable(T::Boolean)` unless nil is a genuine third state

```ruby
# Bad – treats false same as nil
if param.present?

# Good – correctly distinguishes false from nil
if !param.nil?
```

_Sources: PR #17040, PR #25118, PR #25945, PR #18815_

### Ruby Idioms

- Use `?` suffix for boolean methods, not `is_` prefix
- Use `select` over `filter` for filtering enumerables (Ruby convention)
- Use `present?`/`any?` over `!collection.empty?` to avoid double negatives
- Use `Hash.new(0)` for counters; use `.tally` over manual counting loops
- Use `case/when` with class names for type dispatch, not chained `if/elsif is_a?`
- Prefer `&.` (safe navigation) over `try` — `try` swallows NoMethodError on non-nil objects
- Use `ensure` for cleanup that must run regardless of exceptions
- Avoid assignment inside `if` conditions — assign first, then check (Rubocop: `Lint/AssignmentInCondition`)
- Use `**kwargs` as the conventional name for keyword splat parameters
- Ruby hash `[]` returns `nil` for missing keys (unlike Python's `KeyError`) — don't add rescue blocks for conditions that can't occur

```ruby
# Bad
items.map { |i| classify(i) }.each_with_object(Hash.new) { |k, h| h[k] = (h[k] || 0) + 1 }

# Good
items.map { |i| classify(i) }.tally
```

_Sources: PR #20972, PR #21331, PR #21625, PR #21575, PR #26156, PR #18445, PR #23898, PR #21574, PR #17607, PR #21426, PR #18654, PR #20416_

### Naming Conventions

- Avoid `get_`/`find_` prefixes on methods — use descriptive names (`for_entity`, `active`)
- Don't name service methods after AR query methods when semantics differ
- Name hash variables with `_by_key` pattern (e.g., `entity_by_id`)
- Boolean columns: no `is_` prefix — AR generates `.column?` predicates automatically
- Name classes after specific variants, not generic categories
- Use Ruby namespacing (`TreasuryEvent::DeadLetter`) over flat prefixed names
- Avoid Hungarian notation in Ruby — use plain descriptive names, not type-prefixed names
- When a method is scoped to specific entity types, reflect that in the name or add prominent documentation

```ruby
# Bad
def get_active_members; end
entities = {} # hash keyed by id

# Good
def active_members; end
entity_by_id = {}
```

_Sources: PR #23596, PR #19094, PR #22209, PR #17128, PR #25133, PR #24636, PR #18218, PR #17964, PR #18218, PR #24733_

### Sorbet Type Safety

- New files: minimum `# typed: true`, never `# typed: false`; don't use `strict` in specs
- Avoid `T.untyped` when concrete types are known; use `T::Struct` over loose hash types
- Use `SorbetTypes::Unsafe::DateOrTime` for date/time params; compose type aliases from existing ones
- Prefer `.first!`/`.last!` over `.first` + `T.must` — better errors (`RecordNotFound`)
- Use `T.cast` to narrow union types, not `is_a?` guards (which change runtime behavior) or `T.unsafe`
- Fix upstream signatures rather than using `T.cast` at call sites
- Avoid `.checked(:never)` — it disables runtime type checking
- Use `.void` for methods whose return values are not consumed by callers
- Adding `void` signatures to existing methods can break tests asserting on the return value — update tests or reconsider the return type
- When using `T.must`, assert once by extracting to a local variable rather than repeating at every usage
- Use `is_a?` for Sorbet type narrowing, not `.in?([...])` — Sorbet narrows types after `is_a?` but not after `.in?`
- Compose Sorbet type aliases from existing aliases rather than duplicating inline type unions
- When mapping nilable attributes then calling `first!`/`last!`, insert `.compact` before `.sort` to give Sorbet a non-nilable element type
- Pre-commit hooks (like Rubocop autocorrect) can silently change Sorbet sigils (e.g., `# typed: true` → `# typed: strict`); review autocorrected sigil changes

```ruby
# Bad – T.must on AR result
investment = T.must(Investment.where(active: true).first)

# Good – bang method with domain error
investment = Investment.where(active: true).first!
```

_Sources: PR #21222, PR #26103, PR #26101, PR #21319, PR #23811, PR #26503, PR #21290, PR #17046, PR #26312, PR #26193, PR #25118, PR #18580, PR #23830, PR #24584, PR #26408, PR #19604, PR #19466, PR #18205, PR #21070, PR #26312, PR #26193_

### Sorbet with Rails Dynamism

- Add RBI shim files for dynamically-generated Rails methods (route helpers, etc.) instead of `T.unsafe`
- `extend T::Sig` is no longer required; avoid redundant YARDdoc tags that duplicate Sorbet sigs
- When using `T.let` with `.freeze`, place `.freeze` inside the `T.let` expression
- Avoid `public_send` in typed code — it bypasses type checking entirely

```ruby
# Bad – T.unsafe for route helpers
T.unsafe(self).edit_campaign_path(campaign)

# Good – add to sorbet/rbi/shims/routes.rbi
sig { params(campaign: Campaign).returns(String) }
def edit_campaign_path(campaign); end
```

_Sources: PR #17552, PR #25011, PR #23758, PR #26188, PR #26103_

### ActiveRecord Model Conventions

- Use `create!` over `new` + `save` — fail-fast and greppable
- Use `update!` over `update_attribute!` — don't skip validations
- Use `dependent: :destroy` by default, not `dependent: :delete_all` (bypasses callbacks)
- Keep `belongs_to` required (the Rails default) unless the FK is genuinely optional
- Use Rails conditional callback syntax: `before_save :method, if: :field_changed?`
- Use `previously_new_record?` over `id_previous_change` for checking if just created
- Use `params.require` for mandatory param validation, not manual nil checks
- Prefer Rails built-in validators (`validates :field, uniqueness: { scope: [...] }`) over custom validation logic
- Don't combine `optional: true` with `presence: true` on `belongs_to` — they contradict each other

```ruby
# Bad – skips validations, silent corruption
record.update_attribute!(:status, 'closed')

# Good – validates, raises on failure
record.update!(status: 'closed')
```

_Sources: PR #17268, PR #21926, PR #25860, PR #23814, PR #24883, PR #21655, PR #21926, PR #24806, PR #19132_

### Zeitwerk and Autoloading

- File paths must exactly match constant hierarchy — `fix_service.rb` for `FixService`
- Register acronyms via `inflect.acronym('USVC')` in the inflections initializer
- Helpers in `app/helpers/` are auto-loaded; helpers outside won't be available without explicit includes
- Respect Packwerk boundaries when reorganizing code between packages

```ruby
# Bad – file name doesn't match class
# app/services/fixes_service.rb
class FixService; end

# Good – file name matches class
# app/services/fix_service.rb
class FixService; end
```

_Sources: PR #17494, PR #21053, PR #20267, PR #18030_

### Database Column Design

- Use `datetime`/`Time.current` for timestamps, not `date`/`Date.current`
- Name columns specifically for current scope (`treasury_transfers_synced_at`), not optimistically generic
- Use the project's enum pattern (enumerize + Sorbet enum) for enum columns, not raw strings
- Rails validations: `allow_nil` is a top-level option on `validates`, not nested inside `inclusion`

_Sources: PR #24927, PR #23862, PR #20870, PR #23718_

### Avoid Metaprogramming

- Use `attr_accessor`/`attr_reader` instead of `instance_variable_set`/`instance_variable_get`
- Never use `send` to access private controller methods from services — extract shared logic
- Avoid `public_send` for dynamic dispatch when methods are known — use explicit calls or case statements
- Don't memoize class methods with `||=` on the singleton — values persist forever and leak memory
- Prefer the immutable-chain pattern for query builders (each condition returns a new instance) over cloning a mutable base

```ruby
# Bad – meta-programming bypasses encapsulation
obj.instance_variable_set(:@balance, computed_balance)

# Good – explicit accessor
class Transaction
  attr_accessor :running_balance
end
```

_Sources: PR #18122, PR #18521, PR #18535, PR #17964, PR #20972, PR #19857_

### Nil Coercion Gotchas

- Ruby kwarg defaults don't apply when `nil` is passed explicitly — add fallback in method body
- Avoid `.to_f`/`.to_i` on potentially nil values used as hash keys — `nil.to_f` silently becomes `0.0`
- When using `||=` for external identifiers, it prevents accidental overwrites from retries
- Hash string vs symbol keys are not interchangeable — use `with_indifferent_access` when sources vary

```ruby
# Bad – kwarg default doesn't protect against explicit nil
def resize(max_dimension: 1024)

# Good – fallback in body
def resize(max_dimension: nil)
  max_dimension = max_dimension || 1024
end
```

_Sources: PR #21142, PR #18670, PR #20108, PR #17238_

### Logging and Observability

- Never use `puts` in production code — use `Rails.logger` or the error tracker
- Route errors through the centralized error tracker (Sentry) — it falls back to local logging in dev
- Keep metric tags framework-agnostic so dashboards work across all services
- Store raw input payloads (XML, JSON) alongside sync records for debugging

_Sources: PR #20284, PR #20386, PR #22088, PR #23263, PR #25262_

### ActiveRecord Association Safety

- Add nil guards for associations pointing to soft-deleted records even when Sorbet types say non-nil
- Avoid caching transient state (tempfiles) on AR models — let services manage temporary resources
- Don't use `dup` to create records when you only need a subset of columns — use explicit `create!`
- Don't use `Model.last` as a proxy for "the relevant record" — look up through proper associations
- When fetching "latest" by a non-default column, use `.reorder(:column).last` explicitly

```ruby
# Bad – returns random user, potential data leak
user = User.last

# Good – proper association lookup
user = investment.account.user
```

_Sources: PR #24033, PR #21344, PR #22943, PR #19816, PR #17419, PR #18001_

### NOT IN Performance

- Avoid large `NOT IN (...)` subqueries — they generate massive SQL and hurt performance
- Use `LEFT JOIN` with `WHERE joined_table.id IS NULL` instead

```ruby
# Bad – huge IN list
Member.where.not(id: closed_member_ids)

# Good – anti-join pattern
Member.left_outer_joins(:closures).where(closures: { id: nil })
```

_Sources: PR #26240_

### Controller Patterns

- `redirect_to` inside a helper method does not halt the calling controller action — use `redirect_to ... and return` at the action level
- When controller actions need different HTTP statuses per handler, use a typed response struct with an enum
- Never reference production IDs in code comments or test files
- Always chain `.deliver_later` or `.deliver_now` when invoking Rails mailers — without it, the mail is silently discarded

_Sources: PR #18398, PR #26469, PR #26526, PR #17601_

### Document Non-obvious Workarounds

- When introducing AR `.reload` calls that look redundant, add a comment explaining what breaks without it
- When using `+""` to create mutable copies under `frozen_string_literal: true`, comment the intent
- When `find_or_create` handles multiple creation paths with different scoping assumptions, document the reasoning
- When passing unpersisted/virtual AR objects to methods that normally work with persisted records, make this explicit
- Comments should explain *why* code exists or why a non-obvious approach was chosen; delete comments that just describe what the code does

```ruby
# Bad – looks like dead code, someone will "optimize" it away
campaign.reload

# Good – explains the workaround
# Reload required: cached association state is stale after
# the batch update above; without this, status reads are wrong.
campaign.reload
```

_Sources: PR #22680, PR #22890, PR #20557, PR #20564, PR #24883_

### Derive Values, Don't Pass Redundant Parameters

- Don't pass booleans that can be computed from objects already in scope — derive them instead
- Prefer computed methods (ending in `?`) over stored `const` fields on structs when the computation is cheap
- Services should own lookups for domain data they manage, not require callers to pre-fetch and pass it

```ruby
# Bad – derivable boolean passed as separate arg
def process(member:, is_rolling_fund:)

# Good – derive from existing object
def process(member:)
  rolling = member.membership_class.llc.rolling_fund?
end
```

_Sources: PR #18866, PR #23916_

### Scope Queries to Specific Context

- Scope lookups to the specific record in context, not broader fallback queries
- When refactoring query methods, verify whether optional parameters are always provided — eliminate dead branches
- When aggregating across entity hierarchies, be precise about which entity's records you include

```ruby
# Bad – falls back to all LP entities, showing unrelated data
entities = closing.investment_entity || lp.investment_entities

# Good – scoped to closing's entity only
entity = closing.investment_entity
```

_Sources: PR #26206, PR #22454, PR #18878, PR #22191_

### RSpec Test Hygiene

- Use `Timecop.freeze(time) do...end` block form instead of `freeze`/`return` pairs — guarantees cleanup on exceptions
- Rely on `DatabaseCleaner` for test data cleanup, not manual `delete_all`/`destroy_all` in setup
- Avoid `allow_any_instance_of` — extract logic into a service for clean dependency injection and mocking

```ruby
# Bad – cleanup not guaranteed if test raises
Timecop.freeze(Time.zone.now)
# ... test ...
Timecop.return

# Good – block form guarantees cleanup
Timecop.freeze(Time.zone.now) do
  # ... test ...
end
```

_Sources: PR #26275, PR #24550_

### Typed Structs for Return Values

- Use `T::Struct` over `T::Hash[Symbol, T.untyped]` for method return values with known keys
- Group related parameters (e.g., filename + contents) into a `T::Struct` instead of separate args
- Keep structs at a single level of abstraction — don't mix parent-entity and child-entity fields
- For simple success/error returns, use `T.nilable(String)` (nil = success, string = error)
- Prefer `T::Struct` over Sorbet shape types — shapes have limited support and weaker guarantees

```ruby
# Bad – loose hash, no type safety
sig { returns(T::Hash[Symbol, T.untyped]) }
def process = { success: true, data: result }

# Good – typed struct
class ProcessResult < T::Struct
  const :success, T::Boolean
  const :data, T.nilable(String)
end
```

_Sources: PR #23916, PR #24584, PR #23830, PR #19557, PR #26469_

### Reuse Existing Domain Services

- Before implementing new logic, search for existing service methods that handle the same domain concern
- When adding business logic that overlaps with existing code, refactor to a single source of truth
- Duplicating domain logic across services causes silent drift when business rules change in one place

```ruby
# Bad – reimplements lead contact logic that already exists
def find_lead(mc)
  mc.contacts.find { |c| c.role == 'lead' }
end

# Good – reuse canonical service
CPTR::MembershipClasses::InfoService.lead_contact(mc)
```

_Sources: PR #17964, PR #24876_

### Date/Time at API Boundaries

- Pass ISO 8601 strings to the frontend; let the client handle display formatting
- Use `SorbetTypes::Unsafe::DateOrTime` for date/time return types — Rails silently converts between time types
- When gating behavior on a date, handle nil with safe navigation: `date&.future?`

```ruby
# Bad – backend formats for display
sig { returns(String) }
def completed_at = investment.completed_at.strftime('%B %d, %Y')

# Good – pass ISO string, frontend formats
sig { returns(SorbetTypes::Unsafe::DateOrTime) }
def completed_at = investment.completed_at
```

_Sources: PR #18130, PR #26103, PR #26548_

### Packwerk Module Boundaries

- In packwerk-modularized monoliths, use internal public API function calls over networked API calls for in-process data
- Respect Packwerk package boundaries when moving code — satisfying Rails conventions can introduce dependency violations
- Network calls add latency, failure modes, and complexity unnecessary for in-process communication

_Sources: PR #23470, PR #20267_

### Ruby Collection Performance

- Chaining non-mutating array methods (`.compact`, `.flat_map`, `.uniq`) creates a new array at each step — for large collections, prefer bang variants or `.lazy`
- Use `compact!`, `flat_map!`, `uniq!` to mutate in place and avoid intermediate allocations
- Profile memory when processing large datasets with multiple chained transforms

```ruby
# Bad – three intermediate arrays allocated
records.compact.flat_map { |r| r.items }.compact.uniq

# Good – no intermediate allocations
records.lazy.flat_map { |r| r.items }.reject(&:nil?).to_a.uniq!
# Or use bang methods when safe to mutate:
records.compact!; records.flat_map!(&:items); records.compact!; records.uniq!
```

_Sources: PR #22608_
