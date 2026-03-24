# PR Review Mining: Nova Highlights

Mined **5,026 review threads** from **4,193 merged PRs** (March 2025 - March 2026) and synthesized **257 review practices** across **30 topics**.

## By the Numbers

| Metric | Value |
|--------|-------|
| PRs scanned | 4,193 |
| Review threads analyzed | 5,026 |
| Insights extracted | 758 (15% yield — 85% filtered as nits/unresolved) |
| Insights validated against live code | 757 passed, 1 rejected (99.9%) |
| Final practices | 257 across 30 topics |

## Top 10 Most-Enforced Patterns

These are the patterns our reviewers flag most often, ranked by how many independent PRs triggered the same feedback:

### 1. Avoid Type Assertions (15 PRs)
Stop using `as`, `as any`, `as unknown`. Prefer type narrowing, validated return types, or Zod parsing.

### 2. Consolidate Utilities Into Shared Modules (14 PRs)
Before writing a new helper, search `packages/core`, `packages/std.ts`, and `lib/` for existing implementations. Duplicated date formatters, money helpers, and string utilities are the #1 code duplication source.

### 3. Never Silently Swallow Errors (10 PRs)
`void somePromise()` discards errors with zero logging. Fire-and-forget `catch(() => {})` blocks, unchecked mutation results, and silent null fallbacks all hide production issues.

### 4. Co-locate GraphQL Fragments (8 PRs)
Each component declares its own fragment. Parent queries spread child fragments. Types derive from generated fragment types, never manually defined. No shared query files.

### 5. Use Typed, Transport-Agnostic Errors (7 PRs)
Define errors as tagged types (`ServiceTaggedError`) with camelCase names. Namespace under a single import per service. Keep error definitions in the service layer, not GraphQL.

### 6. Log with Context (7 PRs)
Always pass the `error` object to logger (not just `error.message`). Include entity IDs and operation context. Log at the layer that has context, not at every catch.

### 7. Reuse Design System Components (7 PRs)
Before building custom popovers, tooltips, or layout patterns — check ADAPT. Use `AnchoredPopover`, `usePopoverTrigger`, `ComboBox`, `FormModal` from the design system first.

### 8. Transaction Boundaries Matter (6 PRs)
Use `ensureTransaction()` wrapper that accepts an existing tx client. Never make external API calls inside a DB transaction. Always pass the transaction client explicitly.

### 9. Runtime Validation Over Type Casting (6 PRs)
For external data (API responses, form inputs, URL params), use Zod `.parse()` / `.safeParse()` and derive types with `z.infer<>`. Never `as SomeType` on data you don't control.

### 10. Every Resolver Needs an Auth Check (5 PRs)
Use `.withAuth` scopes or `authScopes` on every resolver. No resolver should be accessible without explicit permission. Track `// TODO: add auth` with ticket links for temporary gaps.

## Topic Breakdown

| Topic | Practices | Key Theme |
|-------|-----------|-----------|
| react_state | 16 | useEffect discipline, React Hook Form patterns, Apollo cache |
| react_components | 15 | Reuse ADAPT, guard rendering, shared component APIs |
| typescript_patterns | 15 | No `as` casts, Zod validation, discriminated unions |
| data_integrity | 14 | Transaction boundaries, race conditions, upsert correctness |
| migration_safety | 14 | Prisma naming, enum changes, backfill transactions |
| performance | 14 | Push filtering to DB, batch operations, cap concurrency |
| error_handling | 15 | Silent failures, Result types, typed errors, logging |
| graphql_schema | 13 | Layer hierarchy, thin resolvers, fragment colocation |
| testing_patterns | 13 | Edge cases, E2E fixtures, mock hygiene |
| api_design | 12 | Function signatures, boundary validation, domain naming |
| auth_permissions | 11 | Auth on every resolver, permission levels, server enforcement |
| rails_patterns | 9 | Layer separation, guard clauses, atomic operations |
| code_organization | 9 | Shared modules, no catch-all files, resource grouping |
| naming_conventions | 8 | Provider-agnostic names, singular tables, semantic field names |
| financial_correctness | 6 | Cent-based math, transfer modeling, null vs zero |
| temporal_workflows | 5 | Workflow idempotency, activity serialization, health probes |

## Sample Practice: GraphQL Layer Hierarchy

> **Rule:** Maintain strict import order: `data -> lib -> schema/resolver`
>
> - `lib` must not import from `schema`; `schema` must not import from `data` directly
> - Data layer returns raw results; lib handles transforms; schema handles GraphQL shape
> - Restrict direct Prisma calls to the data layer only
>
> ```ts
> // Bad — lib importing from schema
> import { SomeSchemaType } from '../schema/types'
>
> // Good — schema imports from lib
> import { rawData } from '../lib/someService'
> ```
>
> _Sources: PR #5485, PR #6166, PR #4490_

## How to Use These Rules

**For AI code review** — feed the relevant section into your reviewer's system prompt:
```ts
const rules = await Bun.file('/path/to/rules/sections/graphql_schema.md').text();
systemPrompt += `\n\n## Review Rules\n\n${rules}`;
```

**For team reference** — browse `/Users/yewonlee/src/al-pr-review/rules/sections/` or share this doc.

**For onboarding** — new engineers read the top 10 list above + the topic most relevant to their first task.

---

*Generated by al-pr-review from 4,193 Nova PRs on 2026-03-18*
