---
scope: all
---

# Data Access Layer

### Encapsulate the ORM

- Wrap all ORM calls in data layer functions — no raw Prisma queries in application code
- Define your own Result/error types at the data layer boundary; don't leak ORM types to consumers
- Default to fetching full records; avoid premature `select` field picking that proliferates near-duplicate query functions
- Thin wrappers are fine — consistency matters more than conciseness

```ts
// Bad — raw ORM in application code
const org = await prisma.organization.findUnique({ where: { id } });

// Good — data layer with domain error types
const org = await data.organization.findBy({ id });
```

_Sources: PR #4782, PR #4921, PR #4960_

### Result Types Over Throwing Conventions

- Use `Result<ErrType, ValType>` to encode success/failure in the type system
- Prefer `findUnique` + `resultFromPrisma().andThen(firstOrNotFoundError(...))` over `findUniqueOrThrow`
- Establish get/find naming: `get` throws on missing, `find` returns optional — but Result types are preferred over either convention
- Prefer `Result` over `Either` — success/error semantics are clearer than left/right

```ts
// Bad — raw Prisma throw with opaque error
const record = await prisma.table.findUniqueOrThrow({ where: { id } });

// Good — domain-specific Result
const result = await resultFromPrisma(
  prisma.table.findUnique({ where: { id } })
).andThen(firstOrNotFoundError("Table", id));
```

_Sources: PR #4782, PR #4921, PR #5041_

### Function Signatures and Naming

- Use the module namespace for domain scoping: `data.organization.findBy(...)` not `getOrganizationBy(...)`
- Use arg objects with named keys over positional parameters: `deleteBy({ revisionId })` not `deleteByRevision(revisionId)`
- Optimize for the caller's experience, not the implementer's convenience
- Add explicit return type annotations on all exported data layer functions

```ts
// Bad — positional args, verbose name
export function getOrganizationSettingsMustExistByTransactionId(txnId: string) { ... }

// Good — namespaced, arg object, explicit return
export function getSettingsOrThrowBy({ transactionId }: { transactionId: string }): Promise<Result<NotFoundError, Settings>> { ... }
```

_Sources: PR #4782_

### Transaction Client Must Be Explicit

- Require the database client as a mandatory parameter — never default to a global client
- Optional client parameters are a footgun: callers forget to pass the transaction client and silently bypass isolation

```ts
// Bad — optional client defaults to global
async function create(data: Input, client = prisma) { ... }

// Good — client is required
async function create(data: Input, client: PrismaClient) { ... }
```

_Sources: PR #4782_

### File Organization

- One file per database table in the data layer
- Keep each table's queries in its own file even if they relate to another table's logic
- This makes data access patterns discoverable via consistent naming (`data.<table>.<method>`)

_Sources: PR #4921_

### Update Operation Types

- Prefer `Partial<T>` over `Pick<T, ...>` for update input types when there is no strict reason to limit updatable fields
- `Pick` forces callers to enumerate allowed fields upfront, creating maintenance overhead every time a new field becomes updatable

_Sources: PR #4960_
