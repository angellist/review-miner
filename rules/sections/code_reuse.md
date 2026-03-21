---
scope: all
---

# Code Reuse

### Search Before You Build

- Before adding a utility function, helper, or formatter, search the codebase for existing ones with overlapping functionality
- Check shared libs (`lib/money`, path builders, validation utils) — the function you need likely already exists
- If an existing function is close but not quite right, extend it rather than creating a parallel version

```typescript
// Bad — manual formatting when a helper exists
const display = `$${(amount / 100).toFixed(2)}`

// Good
import { formatMoney } from 'lib/money'
const display = formatMoney(amount)
```

_Sources: PR #5198, PR #5491, PR #5618, PR #2893, PR #5465_

### Extract Duplicated Small Utilities

- When validation regex, normalization functions, or small helpers are copy-pasted between files, extract to a shared location
- Duplicated logic diverges over time — one copy gets fixed, the other doesn't
- Accept the cost of updating call sites upfront to avoid long-term inconsistency

```typescript
// Bad — regex duplicated in each component's constants
// ComponentA/constants.ts
export const ALPHANUMERIC = /^[a-zA-Z0-9]+$/
// ComponentB/constants.ts
export const ALPHANUMERIC = /^[a-zA-Z0-9]+$/

// Good — single source of truth
// lib/validation.ts
export const ALPHANUMERIC = /^[a-zA-Z0-9]+$/
```

_Sources: PR #5688, PR #5198, PR #5465_

### Use Existing Type Guards Over Inline Checks

- Before writing inline type-checking logic, check if a type guard already exists in shared utility libraries
- Express the actual domain intent: prefer `!isMoney(value)` over `isString(value)` when distinguishing money from non-money
- Shared type guards stay correct when the underlying type changes; inline checks silently break

```typescript
// Bad — inline structural check
if (typeof value === 'object' && 'amount' in value && 'currency' in value) { ... }

// Good — dedicated type guard
import { isMoney } from 'lib/money'
if (isMoney(value)) { ... }
```

_Sources: PR #5938_

### Presentation Logic Stays Out of Shared Core

- Don't place display labels, formatted strings, or enum-to-human-readable mappings in shared core libraries
- Different consumers need different formatting — co-locate labels with their usage
- Only promote to shared code when there is a concrete, current need across services

```typescript
// Bad — display labels in core lib
// packages/core/status.ts
export const STATUS_LABELS: Record<Status, string> = { active: 'Active', ... }

// Good — labels live in the consuming app
// apps/sender/constants/statusLabels.ts
export const STATUS_LABELS: Record<Status, string> = { active: 'Active', ... }
```

_Sources: PR #5220_

### Extract Cross-Service Patterns Into Shared Packages

- When infrastructure code (env var injection, config loaders, API clients) is copy-pasted across multiple services in a monorepo, extract into a shared internal package
- Duplicated infra code drifts silently — one service gets a fix, others don't
- Extract early, before the copies diverge

_Sources: PR #6053_
