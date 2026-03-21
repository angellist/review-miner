---
scope: fullstack
---

# Api Design

### Function Signature Conventions

- Use object params (`findBy({ entityId })`) over positional args for data-access and helper functions with 2+ parameters
- Keep pass-through context (`ctx`) as a separate first parameter: `fn(ctx, { arg1, arg2 })`
- Avoid boolean kwargs that fundamentally change behavior — use separate named methods (`create` vs `findOrCreate`)

```ts
// Bad
findByEntityId(id)
fn({ ctx, entityId, amount })
create({ ..., idempotent: true })

// Good
findBy({ entityId: id })
fn(ctx, { entityId, amount })
create({ ... })  // vs findOrCreate({ ... })
```

_Sources: PR #5409, PR #5006, PR #3215, PR #4339_

### Validate at the Boundary

- Parse and validate API parameters at the endpoint boundary using Zod schemas, not inside downstream business logic
- Validate route parameters with Zod schemas rather than trusting raw URL values
- By the time a function is called, parameters should already be correctly typed
- When removing a server-side validation layer, verify equivalent validation exists elsewhere (frontend, upstream service); document where responsibility shifted

```ts
// Bad — validation buried in business logic
function processOrder(params: Record<string, string>) {
  const id = parseInt(params.campaignId); // deep inside
}

// Good — validated at entry
const schema = z.object({ campaignId: z.coerce.number() });
const params = schema.parse(req.params);
processOrder(params); // already typed
```

_Sources: PR #3539, PR #5430, PR #24802_

### Precise Parameter Types

- Prefer specific types (`int32`) over loose unions (string that could be ID or slug) for internal APIs with known consumers
- When a TypeSpec model references an external enum, verify it matches the actual values from the source service
- In non-Rails codebases, use idiomatic naming: "get"/"fetch" for single resources, "list" for collections — not "show"/"index"

_Sources: PR #3666, PR #4872_

### API Surface Hygiene

- Filter out soft-deleted records by default; don't expose tombstone fields to consumers
- Pre-sort at the query level rather than exposing internal ordering keys
- Scope hierarchical data (folders/files) correctly so nested items don't leak into top-level results
- When filters are accepted, verify every filter param actually drives the query — silently ignoring params is a common bug
- When building filters against a search index (Typesense, Elasticsearch), ensure the filter key matches the indexed field exactly — composite/surrogate IDs may differ

```ts
// Bad — exposes internals
t.relation("files", { orderBy: { orderKey: "asc" } })
  .expose("orderKey") // leaks implementation detail

// Good — pre-sorted, no internal fields exposed
t.relation("files", {
  query: { where: { deletedAt: null }, orderBy: { orderKey: "asc" } }
})
```

_Sources: PR #4861, PR #5357, PR #6661, PR #3462_

### Server Owns Context and Business Logic

- Don't pass current-user data from client to server when the server already has it in session/context — expose dedicated resolvers (e.g., `selfOrganizationMember`)
- Filter archived/inactive entities on the backend by default, with an opt-in flag for admin UIs
- Construct display-oriented data (terms, metadata lists) on the backend and expose a generic list type, rather than leaking storage fields

```graphql
# Bad — frontend filters archived members, assembles terms from raw fields
query { orgMembers { id, archivedAt } }
query { deal { term1Title, term1Desc, term2Title, term2Desc } }

# Good — backend handles it
query { activeOrgMembers { id } }
query { deal { terms { title, description } } }
```

_Sources: PR #3004, PR #5443, PR #3094_

### Domain-Neutral Naming

- In shared platform features, avoid embedding domain-specific terminology (e.g., LP/GP) into identifiers — use generic role names (requester, recipient)
- Ensure variable/field names accurately reflect semantics — rename when the meaning changes (e.g., `canInvest` → `has_stopped_for_user`)
- Name data-layer functions by intent (`fetchInteractionsPrioritized`), not by consumer (`fetchForHydration`)

_Sources: PR #4267, PR #3094, PR #6281, PR #4603_

### Avoid Null for Boolean-Like Returns

- When a consumer treats `null` and `false` identically, return `false` instead of `null`
- Use an enum or reason field to communicate the "why" behind a false result

```ts
// Bad — unnecessary ternary state
function isEligible(): boolean | null { return null; }

// Good — clear contract
function isEligible(): { eligible: false; reason: "PAYMENT_MISSING" } | { eligible: true }
```

_Sources: PR #6661_

### Service Gateway Boundaries

- Service gateways (functions calling external services) should accept resolved identifiers as parameters, not perform their own data lookups
- Keep cross-service boundaries clean by pushing ID resolution to the call site

```ts
// Bad — gateway queries internal data layer
async function refill(entityId, accountId) {
  const extId = await dataLayer.findMapping(entityId, accountId);
  return externalService.call(extId);
}

// Good — caller resolves, gateway stays decoupled
async function refill(ipseityEntityId) {
  return externalService.call(ipseityEntityId);
}
```

_Sources: PR #5006_

### Remove Legacy Alongside New

- When adding new functionality that overlaps with a legacy mechanism, remove the old one in the same change
- When adding dual-parameter support (e.g., both ID and handle) to unblock a fix, create a follow-up ticket to consolidate
- For config objects where each instance should deliberately choose its behavior, prefer required fields over optional-with-defaults

_Sources: PR #6855, PR #3232_

### Error Namespacing

- When a service has multiple error types with long repetitive prefixes, namespace them under a single import (e.g., `ExternalBankReferenceError.Authz`)
- In GraphQL, use string enum error types — don't bubble HTTP status codes (404, 500) into the GraphQL error layer
- In `.mapErr` handlers, don't assume only one error type is possible — handle or propagate unexpected errors explicitly

```ts
// Bad
import { ExternalBankReferenceAuthzError, ExternalBankReferenceNotFoundError } from "./errors";

// Good
import { ExternalBankReferenceError } from "./errors";
// usage: ExternalBankReferenceError.Authz, ExternalBankReferenceError.NotFound
```

_Sources: PR #6247, PR #5409_

### REST Endpoint Design

- Place API routes under the controller matching the resource's primary domain concept, not a convenient existing controller
- For access/existence checks, prefer HTTP status codes (200/404/401) over custom response bodies
- Use ES module named re-exports in barrel files — avoid `module.exports` in TypeScript codebases

_Sources: PR #4904, PR #4281, PR #6044_

### Monetary Fields in APIs

- Always document the unit (cents vs dollars) for monetary range filters and financial value inputs
- Associate a currency with numeric monetary fields — abstract ranges without currency context create ambiguity

_Sources: PR #3783_

### Operate at the Correct Entity Level

- When a field belongs to a parent entity, accept the parent ID — not a child ID that forces reduction
- Passing the wrong granularity leads to duplicate work and a confusing API contract

```ruby
# Bad — iterates membership classes to set an LLC-level field
membership_classes.each { |mc| mc.llc.update!(field: value) }

# Good — operate at the LLC level directly
llc.update!(field: value)
```

_Sources: PR #17211_

### Explicit Lookup Precedence

- When supporting multiple lookup strategies (ID, slug, etc.) in a single endpoint, define and document precedence rules
- Always consider the edge case where a slug value could be confused with a numeric ID
- Restore fallback lookups that are removed during refactoring if downstream consumers depend on them

_Sources: PR #21096_

### Include Units in Duration Parameters

- When an API or method accepts a duration parameter, include the unit in the name (e.g., `ttl_ms`, `timeout_seconds`)
- Ambiguous duration parameters lead to misconfiguration — `1000` could mean ms, seconds, or hours

```ruby
# Bad
def acquire_lock(key, ttl: 1000)

# Good
def acquire_lock(key, ttl_ms: 1000)
```

_Sources: PR #22284_

### Split Methods on Nilable Parameters

- When a parameter is sometimes nil and the nil case requires significantly different handling, split into two methods with clear contracts
- Share logic via a private inner method rather than adding defensive nil checks throughout

```ruby
# Bad — nil checks scattered throughout
def carry_hashes(member = nil)
  if member
    # member-specific logic
  else
    # different logic
  end
end

# Good — two explicit public methods
def carry_hashes_for_member(member) ... end
def carry_hashes_for_fund ... end
```

_Sources: PR #23674_

### Domain-Appropriate Identifiers at API Boundaries

- API boundaries should expose domain-appropriate identifiers, not internal implementation details
- When an API conflates different entity types (e.g., closings vs users), it creates tight coupling
- Never pass Active Record objects across Packwerk package boundaries — use the owning package's public API types (DTOs)
- Public API services in `app/public_api/` must not return internal bounded-context types (e.g., `CPTR::*`) — map the result into a neutral struct before crossing the boundary

_Sources: PR #23976, PR #18566, PR #23874_

### Clean Up Serialization Artifacts After Migration

- When migrating inter-service calls to local invocations, revisit the interface for parameters that only existed due to serialization constraints
- Remove redundant parameters that were artifacts of the old architecture (e.g., separate `file` and `file_contents` when the service now receives the file object directly)

_Sources: PR #18604_
