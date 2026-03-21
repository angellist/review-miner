---
scope: all
---

# Code Hygiene

### Reuse Existing Shared Utilities

- Before defining constants, parsers, or helpers inline, check `packages/core/src/` and `lib/` for existing shared modules (bytes, time, order, promise, etc.)
- Use existing constants (e.g., `FILENAME_VARIABLE_SEPARATOR`) instead of hardcoded separator strings
- Use project async utilities (e.g., `reduceSeries` from `lib/promise`) over raw `for...of` loops for sequential processing

```typescript
// Bad — inline constant that drifts from the canonical one
const separator = "___";
const parts = filename.split(separator);

// Good — import the shared constant
import { FILENAME_VARIABLE_SEPARATOR } from "lib/filename";
const parts = filename.split(FILENAME_VARIABLE_SEPARATOR);
```

_Sources: PR #3497, PR #3638, PR #4046, PR #4123, PR #4122_

### Extract Repeated Logic Into Named Helpers

- When the same comparison or small logic block appears 3+ times, extract it into a named helper
- Extract composite key generation (e.g., combining IDs into map keys) into a dedicated function to prevent subtle formatting inconsistencies
- When a lookup map already covers a state-to-value mapping, don't duplicate it in a switch/case — reserve explicit cases for genuinely special logic

```typescript
// Bad — composite key constructed inline in multiple places
const key1 = `${fundId}-${memberId}`;
const key2 = `${fundId}-${memberId}`;

// Good — extracted helper ensures consistency
const makeKey = (fundId: string, memberId: string) => `${fundId}-${memberId}`;
```

_Sources: PR #3556, PR #4043, PR #3966_

### Clean Up Stale Code After Refactoring

- After refactoring, review expressions for leftover defensive code that no longer applies (stale null coalescing, unnecessary type guards, redundant transformations)
- Remove `value ?? null` — it's a no-op that signals leftover code
- Don't commit speculative, unused code; add it when there's a concrete use case

```typescript
// Bad — stale coalescing from before excludedPeopleIds was guaranteed non-null
!(excludedPeopleIds ?? []).includes(id)

// Good — clean expression matching current types
!excludedPeopleIds.includes(id)
```

_Sources: PR #3681, PR #3922, PR #3705_

### Comment Hygiene

- Comments must accurately describe the "why" — misleading comments are worse than no comments
- When applying non-obvious CSS overrides or layout hacks, add a comment explaining intent
- When refactoring or batching existing functions, carry forward explanatory comments that document non-obvious design decisions
- When leaving TODOs, create a tracking ticket (Linear) and reference it in the comment

_Sources: PR #3550, PR #3400, PR #3600, PR #3644_

### No Hardcoded Test Values in Logic

- Review code for hardcoded IDs or test values before submitting PRs — they slip through when developers test against specific data
- When replacing hardcoded strings with constants, consider whether the constant covers all format variations; normalizing data (e.g., title-casing) can be more robust than exact-match comparisons

```typescript
// Bad — hardcoded ID from local testing
if (currentOrganization.id === "org_abc123") { ... }

// Good — dynamic comparison
if (currentOrganization.id === organization.id) { ... }
```

_Sources: PR #3372, PR #3312_

### Consolidate Duplicate Test Fixtures

- Before creating new seed data or test fixtures, check for existing files with similar content
- Consolidate identical data into a single canonical source and reference it from multiple places to avoid maintenance burden and divergence

_Sources: PR #3309_

### Readable Array Pipelines

- Separate eligibility filters from match predicates into distinct `.filter()` and `.find()` calls
- Build conditional multi-step configurations by pushing into an array and mapping, rather than index-based object merging

```typescript
// Bad — combined predicate
members.find(m => !m.removedAt && m.entityId === targetId);

// Good — separated concerns
members.filter(m => !m.removedAt).find(m => m.entityId === targetId);
```

_Sources: PR #3675, PR #4006_
