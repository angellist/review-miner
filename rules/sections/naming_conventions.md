---
scope: all
---

# Naming Conventions

### Consistent Abbreviations

- Pick one canonical abbreviation for each domain concept and enforce it everywhere
- When you find inconsistency, standardize in one pass — don't leave variants

```typescript
// Bad — mixed abbreviations for the same concept
const eebr = getEntityExternalBankReference()
const ebr = getExternalBankReference() // same thing?

// Good — one abbreviation, used uniformly
const ebr = getExternalBankReference()
```

_Sources: PR #6972, PR #6259_

### Descriptive Prefixes over Cryptic Abbreviations

- Spell out prefixes in error codes, identifiers, and namespaces
- Single-letter prefixes save trivial space but require memorization

```typescript
// Bad
throw new Error("s:TRANSFER_FAILED")  // s = service? system?

// Good
throw new Error("service:TRANSFER_FAILED")
```

_Sources: PR #6259_

### Extract Meaningful String Literals to Constants

- Pull semantically significant strings into named constants
- Inline literals are fine for one-off display text, not for identifiers used in logic

```typescript
// Bad
const response = await treasuryClient.request('treasury', path, options)

// Good
const SERVICE_NAME = 'treasury'
const response = await treasuryClient.request(SERVICE_NAME, path, options)
```

_Sources: PR #6259_

### Intent-Oriented Function Names

- Name data-layer functions for what they return, not how one caller uses the result
- Return simple shapes callers can reshape, not consumer-specific structures

```typescript
// Bad — name and return type coupled to one consumer
function fetchForHydration(): HydrationMap { ... }

// Good — intent-oriented, reusable
function fetchInteractionsPrioritized(): { opportunityId: string; interactionKind: string }[]
```

_Sources: PR #6281_

### Propagate Naming Fixes Across Related Entities

- When renaming a field for clarity, audit sibling entities for the same ambiguity
- Inconsistent naming across parallel domain concepts creates confusion

```prisma
// After renaming controlId → controlInstanceId,
// apply the same pattern to the policy side:
// policyId → policyImplId
```

_Sources: PR #6257_

### Follow Existing Naming Conventions in Context

- Before adding a new field, file, or identifier, check how existing peers in the same location name the equivalent
- Consistency across the schema or directory outweighs marginally more precise individual names

```prisma
// Existing models use created_at for both creation and event time
// Bad — adding a separate happened_at diverges from convention
model ActivityLog {
  created_at DateTime
  happened_at DateTime  // redundant given codebase norms
}
```

_Sources: PR #3573, PR #5409_

### Comments Must Match Execution Semantics

- Comments describing concurrency (parallel, sequential, async) must reflect actual behavior
- Misleading concurrency comments can lead devs to "optimize" into race conditions

```typescript
// Bad — comment says parallel, code is sequential
// Run in parallel for speed
await stepOne()
await stepTwo()

// Good — comment explains WHY it's sequential
// It's important that we're NOT running these in parallel!
await stepOne()
await stepTwo()
```

_Sources: PR #6977_

### Generic Copy in Template-Driven UI

- Don't hardcode domain-specific language when the system is generic
- Use configuration or template metadata to drive copy

```tsx
// Bad — investing-specific in a generic transaction flow
<Header>Select your investing entity</Header>

// Good — generic, works for redemptions too
<Header>Select your legal entity</Header>
```

_Sources: PR #3062_

### Boolean Names: Entity Accuracy and Positive Assertion

- Boolean variable names should clearly indicate what entity they describe — `is_scout_fund` not `is_scout` when the flag is about the fund
- Name boolean methods by what they positively assert (`us_based?`) rather than what they negate (`foreign?`)
- Positive assertions avoid double negatives and are easier to extend when new categories are added
- When boolean names appear contradictory (`requires_review` and `should_auto_approve` both true), rename or document the relationship

_Sources: PR #20239, PR #24516, PR #20593_

### Hash Return Convention: foo_by_bar

- When naming hash variables or methods that return hashes, use the `{values}_by_{key}` convention
- Methods named `foo_by_bar` must return a Hash, not an array of pairs — the hash structure enforces uniqueness
- Methods returning scalar values should NOT use this pattern — it implies a hash/dictionary

```ruby
# Bad — name implies hash, returns scalar
def investor_count_by_subscription_id(sub_id)
  42
end

# Good — scalar return, scalar name
def unique_investor_count(sub_id)
  42
end

# Good — hash return matches naming convention
def delay_reason_by_membership_class_ids
  { mc_1: "pending", mc_2: "approved" }
end
```

_Sources: PR #17601, PR #22152, PR #26387_

### Don't Repeat Namespace in Class Name

- When a class lives inside a namespace that already conveys context, don't repeat that context in the class name

```ruby
# Bad — redundant "Cashless"
CPTR::FinancialStatements::Cashless::CashlessScenarioDeterminationService

# Good
CPTR::FinancialStatements::Cashless::ScenarioDeterminationService
```

_Sources: PR #17460_

### ThingService Contains Methods About Thing

- Follow the convention that a `ThingService` contains methods where objects of type `Thing` are the subject
- If a method answers a question about a different entity, it belongs in that entity's service
- Reuse existing shared services for entity data (names, types) rather than reimplementing

_Sources: PR #18409, PR #26443_

### Health Check IDs as Boolean Expressions

- Name health check or validation IDs as boolean expressions where PASS maps to true and FAIL maps to false
- Use `AMENDMENTS_EMPTY` rather than `HAS_AMENDMENTS` when FAIL means amendments exist

_Sources: PR #19495_

### Use Correct Column Types

- Use `date` for date-only values and `datetime` only when time precision matters
- Consistent typing prevents timezone-related off-by-one errors

_Sources: PR #19301_

### Compute Metrics Once, Expose via API

- When backend and frontend independently compute the same metric, ensure they use the same formula
- Inclusive vs exclusive counting is a common source of off-by-one discrepancies
- Ideally, compute once on the backend and expose via API rather than duplicating the calculation

_Sources: PR #25583_
