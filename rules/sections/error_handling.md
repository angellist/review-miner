---
scope: all
---

# Error Handling

### Never Silently Swallow Errors

- Fire-and-forget promises must chain `.catch()` with error reporting — never use `void` to discard promises
- Mutation hooks and service methods must surface errors: throw, return a Result, or display a toast — never silently return
- Silent null checks on expected-present values mask bugs; throw when invariants are violated
- Internal service calls must not swallow errors with a catch-all rescue; return the raw response and let callers handle failures, with logging at the call site
- When handlers catch exceptions and convert them to structured error responses (e.g., bulk APIs), also report to Sentry — the client receiving an error object is not the same as engineers being alerted
- Intentionally suppressed exceptions (not sent to error tracking) must still be logged locally so they're visible in application logs
- Service methods that return domain objects must have their return values captured and threaded through — discarding them silently breaks downstream tracking with no error raised

```ts
// Bad — error silently lost
void syncToVenture(entityId);

// Good — error reported even if not awaited
syncToVenture(entityId).catch(err => errorTracker.report(err));
```

_Sources: PR #5314, PR #5323, PR #5124, PR #3161, PR #4967, PR #7308, PR #3442, PR #6506, PR #4421, PR #5056, PR #20507, PR #6087, PR #6909, PR #6693_

### Result Types: Adopt Bottom-Up, Consume with Tuples

- Introduce Result/ResultAsync starting at the data layer and bubble upward — don't inject mid-stack
- Consume results via `.tuple` destructuring (`const [error, value] = ...`) for explicit error handling
- In resolvers, use exhaustive `switch` on `error._tag` with `ensureExhaustive` for compile-time safety
- Keep raw operations and Result wrapping on separate lines for readability
- Never use `_unsafeUnwrap()` for brevity — the `_unsafe` prefix signals it can throw at runtime; always guard with `isErr()` first

```ts
// Bad — can throw at runtime
const value = result._unsafeUnwrap();

// Good — explicit safe guard
if (result.isErr()) throw result.error;
const value = result.value;
```

_Sources: PR #5323, PR #5334, PR #5204, PR #6247, PR #4879, PR #6353_

### Use Typed, Transport-Agnostic Errors

- Service/domain layers throw typed errors (tagged errors, custom error classes) — not GraphQL or HTTP error types
- Map domain errors to transport errors at the API boundary only
- TaggedError tags use camelCase in this codebase — tag strings must match exactly at definition and comparison sites
- Error messages and type definitions belong with the service error class, not scattered across UI components

```ts
// Bad — GraphQL error in service layer
throw graphQLNotFoundError("Vehicle not found");

// Good — domain error in service, mapped at resolver
throw new ModelNotFoundError("Vehicle", id);
```

_Sources: PR #3211, PR #6012, PR #5931, PR #6302, PR #6921, PR #3950, PR #6247_

### Preserve Error Context When Wrapping

- Always pass `{ cause }` when wrapping or re-throwing errors — losing the original cause makes production issues harder to diagnose
- When parsing external data (JSON, cookies, API responses), re-throw with context about what was being parsed
- When an error handler itself can fail, log both the original error and the handler's error

```ts
// Bad — original cause lost
throw new ServiceError("sync failed");

// Good — cause preserved
throw new ServiceError("sync failed", { cause: originalError });
```

_Sources: PR #6252, PR #2929, PR #2929_

### Exceptions for the Unexpected, Results for the Expected

- Don't use exceptions for expected control flow (e.g., unrecognized enum values, missing optional data)
- Return null, a sentinel value, or a Result type for predictable non-happy-path cases
- When a centralized error handler exists (e.g., prophet handlers), let exceptions bubble up — don't add redundant try/catch
- Prefer `Zod.safeParse()` over `.parse()` when you want callers to handle validation failures gracefully

```ts
// Bad — exception for expected case
if (!KNOWN_STATUSES.includes(status)) throw new Error("Unknown status");

// Good — return value for expected case
if (!KNOWN_STATUSES.includes(status)) return null;
```

_Sources: PR #6447, PR #5931, PR #2929, PR #5145, PR #5123_

### Distinguish Error States in Return Types

- Don't return the same empty value for "no results" and "operation didn't execute" — callers can't tell them apart
- Distinguish error states from expected inactive states in data fetching (e.g., inactive resource vs. fetch failure)
- When a nullable field is intentional, handle null defensively at usage sites rather than changing the schema

```ts
// Bad — empty array for both "no results" and "search skipped"
return [];

// Good — discriminated union
return { success: false } | { success: true, emails: [] };
```

_Sources: PR #5559, PR #7252, PR #3370, PR #3384_

### Log with Context, at the Right Layer

- Always include the error object when logging, not just a descriptive message
- Include contextual identifiers (user ID, entity ID, org ID) in log messages
- Log at the layer with sufficient context — utility functions deep in the stack often lack actionable context
- When throwing in service-level code, log the error at the throw site for observability
- Remove bare `console.log` before merging or convert to structured logs with details
- In pipeline architectures with multiple transformers/middleware steps, catch errors at each step, annotate with the step name, and re-throw — never swallow
- When introducing new filtering or exclusion logic in a data pipeline, add observability (logs, metrics) to quantify how much data is being filtered

```ts
// Bad — no context, no error object
logger.error("sync failed");

// Good — structured context + error
logger.error("venture sync failed", { orgId, entityId, error });
```

_Sources: PR #6299, PR #2965, PR #3001, PR #2982, PR #4897, PR #4037, PR #5101, PR #3735, PR #7418_

### Handle Mutation Errors Before Updating UI

- Check mutation responses for errors before closing modals or updating local state
- Use standardized error-handling helpers (e.g., `useMutationOrToast`) rather than letting mutations fail silently
- Shared mutation hooks should internalize error handling (toast on failure) and expose only the happy-path callback
- Guard against division by zero and other edge cases in UI calculations

```ts
// Bad — optimistic close ignores errors
await updateEntity(input);
closeBlade();

// Good — let Form handle error display
const result = await updateEntity(input);
if (result.errors) throw result.errors;
closeBlade();
```

_Sources: PR #3984, PR #3442, PR #4967, PR #3961, PR #4375_

### Guard Clauses Must Exit

- Guard clauses must always include an explicit `return` or `throw` — a missing return silently falls through
- When `Promise.all` receives a function reference instead of a call, it resolves silently — TypeScript won't catch this

```ts
// Bad — guard without return
if (!entity) {
  logger.error("entity not found");
}
entity.doSomething(); // undefined access

// Good
if (!entity) {
  throw new Error("entity not found");
}
```

_Sources: PR #3024, PR #4674_

### Error Handling Across Service Boundaries

- Match on error codes, not message strings, when handling GraphQL errors on the frontend
- Use framework-provided error types (e.g., `graphQLNotFoundError` in Pothos) at the API boundary
- Separate internal error context from user-facing messages — log the real reason, return a generic error
- Wrap cross-service sync calls in transactions so failures result in clean rollback rather than half-synced state
- A service's public interface must consolidate its error surface — don't let internal sub-service errors (especially authorization errors) leak through unchanged to callers

```ts
// Bad — matching on fragile message string
if (error.message.includes("already exists")) { ... }

// Good — matching on stable error code
if (error.extensions?.code === "ALREADY_EXISTS") { ... }
```

_Sources: PR #3078, PR #3950, PR #3053, PR #4454, PR #4853, PR #6353_

### Defensive Parsing of External Data

- When parsing semi-structured input (cookies, query params, config), wrap individual fields in try-catch so one bad value doesn't break the rest
- When mapping data-layer errors to domain errors, always include a default case for unexpected errors
- Don't add defensive fallbacks for unreachable error cases — prefer fast failure via throw

```ts
// Good — per-field resilience
for (const [key, raw] of Object.entries(cookies)) {
  try {
    parsed[key] = JSON.parse(raw);
  } catch {
    logger.warn("failed to parse cookie", { key, raw });
  }
}
```

_Sources: PR #3148, PR #6247, PR #5123_

### Graceful Degradation in Bulk Operations

- In bulk/list processing UIs, log unexpected items to the error tracker and skip them rather than crashing the entire operation
- Prefer graceful recovery over throwing when a valid recovery path exists (e.g., regenerating a token)
- Use Result monad chaining for multi-step operations to collect errors centrally

```ts
// Good — skip bad items, process the rest
for (const item of items) {
  const result = processItem(item);
  if (result.isErr()) {
    errorTracker.report(result.error, { itemId: item.id });
    continue;
  }
  processed.push(result.value);
}
```

_Sources: PR #3193, PR #5145, PR #5334_

### Assert Impossible States

- When component logic has states that "can't logically happen," add explicit error handling anyway
- When a value is unexpectedly undefined and represents a programming error, prefer throwing over silent logging
- Utility functions should not silently degrade to empty defaults — prefer stricter types so callers handle missing data explicitly
- Place defensive exceptions at API and service boundaries even when current model-layer guards make them unreachable — a future developer extending the model won't necessarily know to update the API layer, and the defensive raise makes that breakage loud

_Sources: PR #4375, PR #4421, PR #5056, PR #5674_

### Staging vs. Production Observability

- Tag notifications from non-production environments with a prefix (e.g., `[staging]`) to distinguish from production
- When consuming IDs from eventually-consistent sources (search indices, caches), log resolution failures for debugging sync drift

_Sources: PR #4853, PR #4037_

### Avoid Boilerplate Error Handling

- Don't add redundant catch/re-throw blocks that add no value — omit optional error handlers (e.g., Effect's `tryPromise` catch param) when just re-throwing
- Reserve `*Async` variants (like `errAsync`) for genuinely async operations — using them for synchronous values is misleading

_Sources: PR #2929, PR #6247_

### Prefer Allowlists Over Denylists for Filtering

- When filtering by type, prefer inclusion (allowlist) over exclusion (denylist)
- Allowlists fail safely when new types are added — they are simply excluded until explicitly opted in
- Denylists silently include new types that may not be appropriate

```ruby
# Bad — new partner types silently included
allocatees.reject { |a| a.partner_type.in?(EXCLUDED_TYPES) }

# Good — only explicitly allowed types pass through
allocatees.select { |a| a.partner_type.in?(ALLOWED_TYPES) }
```

_Sources: PR #23236_

### Fail Loudly on Unexpected States in Financial Services

- In financial services, prefer raising on unexpected states over silent no-ops
- When downstream logic assumes a prior step succeeded, a silent no-op creates a gap where incorrect data flows unchecked
- Validate record counts match expectations and raise on unexpected multiplicity
- When refactoring conditional chains into lookup tables, verify error-handling paths from the original code are preserved — lookup misses that return nil can silently propagate bad data
- When reusing a shared interface across command types, never blanket-set boolean flags to false — each field must reflect actual domain state, or extract a builder that derives correct values from context

```ruby
# Bad — silently returns, downstream assumes success
return if transfers.already_attributed?

# Good — raise so inconsistency is caught immediately
raise "Transfers already attributed" if transfers.already_attributed?
```

_Sources: PR #23468, PR #22635, PR #17665, PR #18607, PR #22563_

### Compute Dirty Checks Before Persisting

- Always compute change-detection comparisons before calling `update!`
- After update, the in-memory model reflects new values, making before-vs-after comparisons meaningless
- Capture the comparison result in a variable before the write

```ruby
# Bad — comparison after update always evaluates as equal
record.update!(fee_percent: new_percent)
sync_downstream if record.fee_percent != old_percent  # always false

# Good — capture before persisting
changed = record.fee_percent != new_percent
record.update!(fee_percent: new_percent)
sync_downstream if changed
```

_Sources: PR #19121_

### Consistent Lifecycle Method Contracts

- Lifecycle methods (e.g., `complete_action!`) should have a consistent persistence contract
- If the convention is that records remain unpersisted after the method call, don't silently add a `save!`
- Restructure to pass data through return values rather than breaking the expected contract

_Sources: PR #18088_

### Gate Side Effects with Explicit Conditions

- Side effects in service methods (emails, syncs) should be explicitly gated by all relevant conditions
- Check whether triggering data was actually created (not just found), which caller invoked the method, and timing
- Use keyword arguments with safe defaults (false) to let callers opt in to side effects

```ruby
# Bad — emails fire unconditionally
def create_segment!(params)
  segment = find_or_create(params)
  send_catch_up_emails(segment)
end

# Good — gated by caller and timing
def create_segment!(params, send_catch_up_emails: false)
  segment = find_or_create(params)
  return segment unless send_catch_up_emails
  return segment if segment.previously_existed?
  return segment if past_ach_pull_date?
  send_catch_up_emails(segment)
  segment
end
```

_Sources: PR #26548_

### Document Non-Obvious Validation Assumptions

- When a validation guard assumes business context (e.g., "tax only operates on year boundaries"), add an inline comment
- Non-obvious invariants that require domain knowledge should be explained so future readers don't reverse-engineer the reasoning
- Reference class names via `.name` instead of hardcoded strings for polymorphic type columns

_Sources: PR #17398, PR #23311_

### Make Ordering Explicit at the Call Site

- When selecting the "latest" or "best" record, use explicit selection (`max_by`, `min_by`, `sort_by.last`)
- Don't rely on implicit ordering from upstream methods — changes there silently break callers
- Always include an explicit `ORDER BY` clause when using cursor-based pagination
- When a method depends on input being sorted, make that assumption explicit through naming, a comment, or an assertion

```ruby
# Bad — relies on implicit ordering
k1_timeline.first

# Good — explicit intent
k1_timeline.select { |t| t.type == :finalized }.max_by(&:created_at)
```

_Sources: PR #22992, PR #5314, PR #18122_

### Avoid Nil-Default Arguments with Destructive Semantics

- Don't default keyword arguments to `nil` when `nil` has destructive semantics (e.g., clears an association)
- Make the argument required so callers must explicitly pass a value — omitting it should not silently delete data
- If `nil` is a valid intentional value, callers should pass it explicitly rather than relying on a default

```ruby
# Bad — omitting the arg silently clears the association
def update_record!(record, linked_id: nil)
  record.update!(linked_id: linked_id)
end

# Good — required arg; callers must be explicit
def update_record!(record, linked_id:)
  record.update!(linked_id: linked_id)
end
```

_Sources: PR #17648_

### Validate Against Pre-Transition State

- When writing validations that run before a state transition, ensure filter criteria match the pre-transition state
- Filtering by a post-transition status (e.g., "approved") causes validations to pass vacuously on empty sets
- Don't add conditional guards to bypass validations at the call site when the underlying service already handles different modes internally

```ruby
# Bad — filters by post-transition status, passes vacuously
payments.where(status: :approved).each { |p| validate_liquidation!(p) }

# Good — validates all payments before approval happens
payments.each { |p| validate_liquidation!(p) }
```

_Sources: PR #22680, PR #20939_

### Verify Collection Cardinality Before Singular Access

- When using `.first` or `.take` on a collection, verify whether the business rule requires processing one or all items
- Using `.first` when all items need processing silently drops records
- In tests, assert collection size before calling `.first` to document the uniqueness assumption

```ruby
# Bad — silently drops the non-QP fund
membership_class_ids.first

# Good — process all items when domain requires it
membership_class_ids.each { |id| file_ein(id) }
```

_Sources: PR #23874, PR #26664_

### Handle Nullable Fields Without Silently Dropping Records

- Don't assume a single date or lookup field is always populated — use a fallback chain of fields to avoid silently excluding records
- When a field is expected but technically nullable, use a descriptive placeholder rather than skipping the record
- Be cautious with early returns on nullable lookups — if downstream logic handles nil or must execute regardless, the short-circuit silently skips it

```ruby
# Bad — silently excludes records where wired_at is nil
assets.where("wired_at BETWEEN ? AND ?", start_date, end_date)

# Good — fallback chain covers nullable fields
assets.where("COALESCE(document_date, signed_at, wired_at) BETWEEN ? AND ?", start_date, end_date)
```

_Sources: PR #17908, PR #23693, PR #17112_

### Don't Add Nil Guards for Non-Nullable Values

- Before adding nil-guard logic, verify whether the value can actually be nil in practice
- Unnecessary nil guards add complexity and mask real bugs by silently handling cases that should never occur
- If a value should always be present, let it raise naturally — don't add fallback logic that creates dead code paths

```ruby
# Bad — lp_rate is never nil; fallback adds dead code
base_rate = lp_rate || default_rate
result = compute(base_rate)

# Good — trust the invariant, keep it simple
result = compute(lp_rate)
```

_Sources: PR #18952, PR #18959_

### Always Sync Fields in Find-or-Create Patterns

- When syncing fields between systems via `find_or_create_by`, always update the synced field — not just when it's blank
- Conditional updates (`update if field.blank?`) cause silent drift when the source value changes
- Treat the external system as the source of truth and overwrite on every sync

```ruby
# Bad — only sets once, drifts if source changes
record = Model.find_or_create_by(external_id: ext_id)
record.update!(name: ext_name) if record.name.blank?

# Good — always sync
record = Model.find_or_create_by(external_id: ext_id)
record.update!(name: ext_name)
```

_Sources: PR #19466_
