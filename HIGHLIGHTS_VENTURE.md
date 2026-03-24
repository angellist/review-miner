# PR Review Mining: Venture Highlights

Mined **9,280 review threads** from **3,362 merged PRs** (March 2025 - March 2026) and synthesized **282 practices** across **20 topics** from the Venture codebase.

## By the Numbers

| Metric | Value |
|--------|-------|
| PRs scanned | 3,362 |
| Review threads analyzed | 9,280 |
| Practices synthesized | 282 across 20 topics |
| Top domain focus | GraphQL, Rails backend, financial correctness |

## Top 10 Most-Enforced Patterns

These are the patterns Venture reviewers flag most often, ranked by how many independent PRs triggered the same feedback:

### 1. Thin Resolvers (20 PRs)
Keep GraphQL resolvers as thin wrappers — no business logic, no switch statements, no validation. Extract argument validation, branching, and domain operations into the service (lib) layer. Don't pass GraphQL input types into services — convert to domain types at the boundary.

### 2. Co-locate GraphQL Fragments (19 PRs)
Each component declares its own fragment. Parent queries spread child fragments. Derive prop types from generated fragment types, never define them manually. Never create shared query files — they couple components that evolve independently.

### 3. N+1 Prevention in Resolvers (17 PRs)
Use dataloaders to batch database queries. Every resolver that touches a relation needs a dataloader path. N+1s are the #1 GraphQL performance problem and they're invisible until production load.

### 4. Consolidate Utilities Into Shared Modules (14 PRs)
Before creating a new utility file, check `lib/money`, `lib/dates`, `lib/string` for existing implementations. Add to the existing module rather than creating standalone files. Rule of three: extract when the same logic appears in three places.

### 5. Never Silently Swallow Errors (11 PRs)
`void somePromise()` discards errors with zero logging. Mutation hooks must surface errors — throw, return a Result, or display a toast. Silent null checks on expected-present values mask bugs.

### 6. Reuse Design System Components (11 PRs)
Before building custom UI — check the design system. Duplicated popovers, tooltips, form modals, and layout patterns are the #1 source of frontend inconsistency in Venture.

### 7. Service Object Conventions (10 PRs)
Centralize complex business logic in service objects. Use `ServiceName.call(args)` pattern. Keep services focused on a single domain operation. This is the backbone of Venture's backend architecture.

### 8. Separate Migrations Into Their Own PRs (9 PRs)
Isolate database migrations from application logic changes. Separate PRs simplify review, enable independent deployment, and reduce the blast radius when a migration fails.

### 9. Transaction Boundaries (6 PRs)
Wrap paired destructive-then-constructive operations in a transaction. Always pass the `tx` client — never use the outer Prisma client inside a `$transaction` callback. Never make external API calls inside transactions.

### 10. Every Resolver Needs an Auth Check (5 PRs)
Use `.withAuth` scopes or `authScopes` on every resolver. Even read-only resolvers need permission validation. Missing auth checks are silent security holes. Track `// TODO: add auth` with Linear ticket links.

## Topic Breakdown

| Topic | Practices | Key Theme |
|-------|-----------|-----------|
| rails_patterns | 34 | Sorbet types, service objects, guard clauses, layer separation |
| migration_safety | 33 | Separate PRs, avoid DB enums, onDelete strategy, backfill safety |
| financial_correctness | 28 | Cent-based math, transfer modeling, null vs zero, strict parsing |
| code_organization | 25 | Shared modules, no catch-all files, domain-scoped naming |
| error_handling | 23 | Silent failures, Result types, typed errors, exhaustive matching |
| graphql_schema | 23 | Layer hierarchy, thin resolvers, fragment colocation, N+1s |
| auth_permissions | 23 | Auth on every resolver, framework mechanisms, permission levels |
| testing_patterns | 23 | Edge cases, E2E fixtures, mock hygiene |
| api_design | 22 | Object params, boundary validation, domain naming |
| react_components | 22 | Design system reuse, guard rendering, conditional readability |
| performance | 20 | Filter in SQL, batch operations, dataloader discipline |
| data_integrity | 19 | Transaction boundaries, race conditions, upsert correctness |
| temporal_workflows | 13 | Workflow idempotency, activity serialization, health probes |
| async_patterns | 8 | Promise chains, concurrent batching, cancellation |
| logging_observability | 8 | Structured logging, entity context, error objects |

## What Makes Venture Different

Venture's review culture reflects its domain — **financial infrastructure with strict correctness requirements**:

- **Rails + Sorbet type safety** is the most-enforced single practice (22 PRs). The team treats Ruby like a statically typed language.
- **GraphQL discipline** dominates the top 3. With a large Pothos + Ruby resolver surface, keeping resolvers thin and fragments colocated is essential.
- **Financial correctness** is a standalone topic with 28 practices — covering cent-based arithmetic, transfer-type modeling, and the critical distinction between null and zero.
- **Migration safety** is enforced heavily (33 practices) because schema changes on a financial platform carry real risk.

## Sample Practice: Transaction Boundaries

> **Rule:** Wrap paired operations in a transaction. Pass `tx` explicitly.
>
> - Never use the outer Prisma client inside a `$transaction` callback
> - Use `ensureTransaction` wrappers so functions compose inside existing transactions
> - Never wrap external API calls inside interactive transactions — they hold a DB connection open
>
> ```ts
> // Bad — mixes transactional and non-transactional clients
> await prisma.$transaction(async (tx) => {
>   await tx.record.update({ ... });
>   await prisma.auditLog.create({ ... }); // uses outer client!
> });
>
> // Good
> await prisma.$transaction(async (tx) => {
>   await tx.record.update({ ... });
>   await tx.auditLog.create({ ... });
> });
> ```
>
> _Sources: PR #3024, PR #3521, PR #3567, PR #3888, PR #4900, PR #5126_

## How to Use These Rules

**For AI code review** — the bot is wired up:
```bash
python -m bot.review --pr 123 --repo venture --dry-run
```

**For team reference** — browse `rules/sections/` for the full practice library.

**For onboarding** — new Venture engineers should start with the top 10 list above, then read `rails_patterns` + `financial_correctness` for backend work, or `graphql_schema` + `react_components` for frontend.

---

*Generated by al-pr-review from 3,362 Venture PRs on 2026-03-19*
