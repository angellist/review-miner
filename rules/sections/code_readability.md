---
scope: all
---

# Code Readability

### Flatten Nesting with Early Returns

- Use early returns and `continue` to reduce indentation depth
- Remove redundant guards before loops — iterating an empty array is a no-op
- For retry-with-limit patterns, prefer recursion with an attempt parameter over while loops with mutable counters

```typescript
// Bad — redundant guard + deep nesting
if (items.length > 0) {
  for (const item of items) {
    if (item.isValid) {
      process(item);
    }
  }
}

// Good — flat, no redundant guard
for (const item of items) {
  if (!item.isValid) continue;
  process(item);
}
```

_Sources: PR #6889, PR #2659_

### Extract Large Modules by Responsibility

- When a file accumulates helpers serving a distinct sub-purpose, extract them into their own module
- Encapsulation and readability outweigh minor gains from co-locating unrelated logic
- Especially important for authorization logic, which must be easy to audit

```typescript
// Bad — hooks file contains both data-fetching and cell renderers
// usePortfolioData.ts (500+ lines mixing concerns)

// Good — split by responsibility
// usePortfolioData.ts (data-fetching hook)
// portfolioCellHelpers.ts (cell renderer functions)
```

_Sources: PR #6905, PR #3215_

### Keep Comments Accurate and Preserve Intent

- Comments about execution semantics (parallel vs sequential) must match the code
- When a field is a proxy for another concept, comment the correlation and its limits
- When complex coordination patterns are justified, document the "why" inline
- When refactoring or moving code, carry explanatory comments with the logic

```typescript
// Bad — misleading comment invites broken "optimization"
// Run all operations in parallel
await stepA();
await stepB(); // actually sequential and must stay that way

// Good — accurate comment prevents mistakes
// Sequential execution is intentional — stepB depends on stepA's side effects
await stepA();
await stepB();
```

_Sources: PR #6977, PR #7092, PR #3034, PR #2652, PR #3215_

### Remove Dead Code Before Review

- Clean up artifacts from abandoned implementation attempts before submitting PRs
- When pivoting approaches (e.g., REST to message queues), remove the abandoned path promptly
- After design decisions are finalized, remove holdover code written under previous assumptions
- Leftover integration code confuses readers and risks unintended side effects

_Sources: PR #7226, PR #3059, PR #3193_

### Name Implicit Assumptions Explicitly

- Extract array index access (`.at(0)`, `[0]`) into named variables with comments explaining why
- Consolidate parallel Maps sharing the same key set into a single Map with tuple/object values

```typescript
// Bad — implicit assumption buried in chained access
const org = investor.organizations.at(0);

// Good — assumption is documented and questionable
// Each investor has exactly one org in this context (single-entity investors)
const primaryOrg = investor.organizations.at(0);

// Bad — two maps with identical keys
const amounts = new Map<string, number>();
const dates = new Map<string, Date>();

// Good — single map, explicit relationship
const paymentInfo = new Map<string, [number, Date]>();
```

_Sources: PR #3062, PR #7299_

### Document Temporary Workarounds

- When using a temporary mechanism (localStorage, in-memory cache) as a stand-in, document which system is the source of truth
- Link to follow-up work so future developers know the current approach is not intentional

_Sources: PR #2652_

### Prefer Simpler Business Logic

- Before adding complexity to filters or conditional logic, verify the requirement with product stakeholders
- Simpler filtering logic is preferable when the business requirements support it
- Don't add complexity for assumed requirements

_Sources: PR #3185_
