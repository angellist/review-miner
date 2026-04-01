---
scope: fullstack
---

# Graphql Schema

### Layer Hierarchy: data -> lib -> schema

- Maintain strict import order: data -> lib -> schema/resolver
- lib must not import from schema; schema must not import from data directly (go through lib)
- Data layer returns raw/untransformed results; lib layer handles generic transforms (snake_case -> camelCase); schema layer handles GraphQL-specific shape transforms
- Restrict direct ORM (Prisma) calls to the data layer only — all other layers use data layer abstractions
- Keep the graph/API layer product-agnostic; product-specific logic lives in its own module
- Domain services must not raise transport-layer errors (e.g., `DetailedExecutionError`); raise domain errors and let the GraphQL layer translate

```ts
// Bad — lib importing from schema
// graph/src/lib/transformers.ts
import { SomeSchemaType } from '../schema/types'

// Good — transformer in schema layer, lib returns raw data
// graph/src/schema/transformers.ts
import { rawData } from '../lib/someService'
```

_Sources: PR #5485, PR #6166, PR #4490, PR #20766, PR #22361_

### Thin Resolvers

- Keep GraphQL resolvers as thin wrappers — no business logic, no switch statements, no validation, no data formatting
- Extract argument validation, branching logic, domain operations, and CSV/report generation into the service (lib) layer
- Data layer should return nullable results; let the resolver/caller decide how to handle missing data
- When multiple resolvers share identical query-building logic, extract it into a shared fetch service immediately
- Don't pass GraphQL input types into service-layer logic — convert to domain types (Sorbet structs/enums) at the boundary using `prepare`
- Validation belongs in the service or model layer, not in resolvers — ensures consistency across all entry points

```ruby
# Bad — business logic in resolver
def resolve(fundraising_campaign_id:)
  fc = FundraisingCampaign.find(fundraising_campaign_id)
  fc.members.select { |m| m.active? }.sort_by(&:name)
end

# Good — delegate to service
def resolve(fundraising_campaign_id:)
  MemberService.active_sorted(fundraising_campaign_id:)
end
```

_Sources: PR #6111, PR #4805, PR #5212, PR #20887, PR #22939, PR #23294, PR #18122, PR #19326, PR #22630, PR #23988, PR #24011, PR #20836, PR #21958, PR #23080, PR #22470, PR #23640, PR #23508, PR #24462, PR #25730, PR #22708_

### Fragment Colocation

- Co-locate GraphQL fragments with the component or hook that consumes the data
- Parent queries spread child fragments — each component declares its own data requirements
- Derive component prop types from generated fragment types, never define them manually
- If a hook (not the component) uses the data, export the fragment from the hook
- Never create shared query files or centralized query directories — they couple components that evolve independently
- Keep fragment definitions in a single location per component — don't split fields across multiple fragment blocks
- Prefer component-specific fragments over shared ones to prevent overfetching as components diverge
- Pass parent fragment objects as props rather than destructuring into many individual props — keeps components coupled to their data requirements

```tsx
// Bad — manual type, no fragment
type UserData = { name: string; email: string }
const UserCard = ({ data }: { data: UserData }) => ...

// Good — fragment + generated type
export const UserCardFragment = gql`
  fragment UserCard on User { name email }
`
const UserCard = ({ data }: { data: UserCardFragment }) => ...
```

_Sources: PR #2698, PR #2667, PR #3681, PR #3884, PR #6285, PR #6365, PR #6845, PR #3985, PR #21896, PR #23015, PR #22763, PR #24289, PR #25099, PR #18322, PR #18332, PR #18582, PR #23731, PR #25707, PR #19686, PR #5513_

### Apollo Cache: Always Include id

- Always select the `id` field in every GraphQL query — Apollo uses `__typename` + `id` for cache normalization
- For models without a natural ID, create a synthetic ID on the backend resolver (e.g., combining entity ID + org ID)
- Omitting `id` breaks automatic cache updates and causes stale data after mutations

```graphql
# Bad — missing id
fragment BankAccount on BankAccount {
  accountNumber
  routingNumber
}

# Good
fragment BankAccount on BankAccount {
  id
  accountNumber
  routingNumber
}
```

_Sources: PR #6570, PR #2667_

### Apollo Cache: Mutations and Updates

- Return the full entity type from mutations so Apollo can auto-update its normalized cache
- For updates, rely on Apollo's automatic cache normalization — don't refetch
- For deletes, use `cache.evict({ id })` + `cache.gc()` instead of refetching
- Prefer returning the affected fragment directly in the mutation response over `refetchQueries` — Apollo's normalized cache updates the component automatically; reserve `refetchQueries` for mutations with wide-reaching side effects across multiple queries
- Before adding `refetchQueries`, verify whether Apollo's cache should already handle the update — investigate root cause (mismatched response shape, incorrect cache logic) first
- For creates, use targeted cache insertion rather than refetching the entire parent query
- Return the affected parent object from mutations so the frontend cache can update children automatically
- Custom mutation hooks should return `[mutationFn, mutationResult] as const` matching Apollo's useMutation API

_Sources: PR #6277, PR #6365, PR #6544, PR #23197, PR #25099, PR #25594, PR #24011, PR #26308, PR #26930_

### Pothos: fieldWithInput and Inline Args

- Prefer `t.fieldWithInput` over `t.field` with manual args for mutations
- Use inline input fields when the input is only used by a single mutation — reduces boilerplate and keeps input co-located
- Only extract a shared input type when it's reused across multiple operations

```ts
// Bad — separate input type for single-use
const UpdateNameInput = builder.inputType('UpdateNameInput', {
  fields: (t) => ({ name: t.string({ required: true }) }),
})

// Good — inline with fieldWithInput
t.fieldWithInput({
  input: { name: t.input.string({ required: true }) },
  resolve: (_, { input }) => updateName(input.name),
})
```

_Sources: PR #5810, PR #3681, PR #3799_

### Pothos: Auth Scoping and ID Convention

- Use `.withAuth` scopes on field definitions to guarantee authenticated context — don't manually null-check `ctx.account`
- Expose ID fields with the project convention: `t.expose("id", { type: "UUID" })`
- Use existing context helpers (e.g., `isImpersonating`) instead of reimplementing request-level checks

_Sources: PR #4098, PR #3696, PR #3080_

### Pothos: Pagination with prismaConnection

- Use `t.prismaConnection` for paginated list fields — it handles cursor management, take/skip, and totalCount automatically
- For totalCount alongside a connection, use the library's built-in third-object option rather than creating a separate resolver
- Ensure all queries in connection helpers go through the data layer, not raw Prisma calls

_Sources: PR #4086, PR #3914, PR #6166_

### GraphQL Error Handling

- Use `graphQLInputError` for validation failures — it associates messages with specific input fields for field-level UI errors
- Don't propagate HTTP status codes through GraphQL; use domain-specific string enums (e.g., `BANK_ACCOUNT_NOT_FOUND`)
- When required data is missing in a resolver, raise an explicit error — never silently return nil or empty defaults
- Always capture GraphQL mutation responses on the frontend and use error-handling utilities (`throwIfGraphQLError`)
- Rescue only specific error classes in mutations — generic `StandardError` rescue blocks hide real bugs
- For private/restricted resource lookups, always return a generic not-found error — returning a specific "inaccessible" error confirms the resource exists and constitutes information disclosure
- Wrap mutation calls in `try/catch` on the frontend; optimistic UI updates can run before `await`, but failures must be caught explicitly — Apollo/urql don't always throw by default in all configurations
- In graphql-ruby, `rescue_from` accepts multiple exception classes as positional args for grouping related handlers; use separate `rescue_from` blocks for unrelated exceptions — they fire in file order, avoiding internal conditional branching

```ruby
# Bad — silent nil on missing data
def resolve(id:)
  record = Model.find_by(id: id)
  return nil unless record  # hides data corruption
end

# Good — fail loudly
def resolve(id:)
  Model.find_by!(id: id)  # raises RecordNotFound
end
```

_Sources: PR #5834, PR #5409, PR #23294, PR #23455, PR #24172, PR #25370, PR #23640, PR #22041, PR #20819, PR #23689, PR #18975, PR #21324, PR #22307, PR #27322, PR #27168, PR #5798_

### Schema Typing: Precision Over Generics

- Use precise GraphQL types — `[String!]!` not `JSON` when the shape is known
- Expose known value sets as GraphQL enums, not raw strings — gives frontend generated TypeScript types
- Use `GraphQL::Types::ISO8601DateTime` for timestamps; avoid custom date types — let clients handle formatting
- For collection/list input fields, prefer non-nullable with empty array default over nullable
- Field nullability declarations must match actual resolver return values — a `null: false` field backed by a nilable method will raise at runtime
- Field types should reflect actual data precision (e.g., Integer for whole-dollar amounts, not Float)
- When multiple domain models share a GraphQL enum, verify they truly share identical valid values — a union catch-all enum silently permits invalid states; prefer per-type enums
- In list/aggregate types, prefer nullable fields when source data quality varies — a single nil shouldn't error the entire result list

```graphql
# Bad — loose typing
type DataRoom {
  tags: JSON
  transactionType: String
}

# Good — precise typing
type DataRoom {
  tags: [String!]!
  transactionType: TransactionTypeEnum!
}
```

_Sources: PR #3681, PR #5464, PR #5377, PR #5968, PR #17700, PR #22824, PR #19043, PR #17849, PR #17966, PR #18094, PR #22923, PR #22078, PR #18287, PR #18301_

### N+1 Prevention in Resolvers

- When a resolved field triggers a DB query, it will N+1 in list/connection contexts — use dataloaders or BatchLoader::GraphQL to batch
- Expensive computed fields should be top-level queries, not resolved fields on parent types, to make cost visible to callers
- Before calling existing service methods inside field resolvers, check what queries they execute internally — methods fine in isolation may N+1 in list context
- Don't add blanket `.includes` in resolvers as a quick fix — resolvers don't know what fields clients will request; use field-level batch loading instead
- Only add preloads to a resolver if the association is required by every query using it; for optional fields, use batch loaders
- When adding fields to widely-used types, consider the blast radius — a new association on a shared type creates N+1s for every consumer
- When adding association traversals in shared concerns, be aware of the N+1 multiplication effect — flag for monitoring and proactively add preloading at known call sites
- When a resolver on an association is consistently slow, check whether the underlying DB table has the necessary index — resolver-level workarounds may hide the root cause
- Use canonical cached attributes (e.g., `cached_fund_inception_date`) rather than recomputing from raw associations in resolvers — recomputing creates N+1s in list context and silently diverges when domain definitions change

```ruby
# Bad — N+1 in list context
field :settings, SettingsType, null: true
def settings
  object.settings  # called per row
end

# Good — BatchLoader
field :settings, SettingsType, null: true
def settings
  BatchLoader::GraphQL.for(object.id).batch do |ids, loader|
    Setting.where(org_id: ids).each { |s| loader.call(s.org_id, s) }
  end
end
```

_Sources: PR #2859, PR #3801, PR #4319, PR #5579, PR #3493, PR #17700, PR #22630, PR #25783, PR #25648, PR #18282, PR #25035, PR #23047, PR #24189, PR #24155, PR #22552, PR #22343, PR #25376, PR #6739, PR #26994_

### Schema Organization

- One resolver per file — don't inline resolvers in index/barrel files
- Namespace admin resolvers and types under a separate admin package — admin types can compose non-admin types, but not vice versa
- All GraphQL types share a global namespace — name with enough specificity to avoid collisions (e.g., `FundraisingCampaignChecklistItemType`, not `ChecklistItemType`)
- Nest related data under the parent type rather than creating top-level query fields with long compound names — follow the graph structure
- Before creating a new type, check if an existing type already covers the fields you need
- Avoid placing slow-to-compute fields in eagerly-loaded root queries (ViewerQuery) — split into dedicated async queries
- Don't create separate types to isolate slow fields — GraphQL resolves fields on demand; performance is controlled by which fields the client queries
- GraphQL connection and type class namespacing should mirror the schema hierarchy — a connection type belongs under the parent type that uses it
- When adding new types that share fields/behavior with existing types (e.g., different parsable document types), define a shared interface to enforce consistency
- Namespace third-party integration queries under their domain rather than polluting the top-level query type
- Delete `.graphql` files when removing their last consumer — orphaned query files accumulate silently and mislead future developers into thinking the type or field is still in use
- Admin/internal list queries should apply an explicit limit even if the table starts small — without a limit, the query silently degrades as data accumulates
- When introducing a new resolver that returns records also surfaced by an existing resolver, verify both use identical filtering criteria — divergent WHERE clauses between count and list queries produce confusing UI discrepancies

_Sources: PR #3080, PR #4946, PR #5425, PR #22554, PR #24068, PR #23750, PR #22763, PR #25400, PR #25982, PR #22581, PR #20684, PR #20887, PR #26763, PR #5540, PR #6870_

### Data Layer Composition

- Don't hardcode `include`/`select` clauses in data layer query functions — let callers specify which relations to load
- When migrating to a data layer abstraction, ensure all queries go through it consistently — no raw ORM models from new code

_Sources: PR #6211, PR #6166_

### Deploy Safety for Schema Changes

- Deploy server-side schema changes before client-side queries — bundling both risks the frontend querying non-existent fields
- When modifying or removing fields, deploy in two phases: (1) add new alongside old, (2) remove old after first deploy is live
- When modifying shared GraphQL fragments that reference new server fields, deploy the backend first in a separate PR
- When modifying GraphQL enums, trace all frontend consumers (switch statements, conditional renders) and update in the same PR
- Only commit auto-generated schema file changes (schema.graphql dumps) that are directly related to your PR — local environment differences cause unrelated diffs in generated files; exclude these to keep PRs reviewable

```
# Phase 1 PR: Add new field, keep old
field :legacyName, String  # keep
field :displayName, String # add

# Phase 2 PR (after Phase 1 is deployed): Remove old
# field :legacyName — removed
field :displayName, String
```

_Sources: PR #17582, PR #17607, PR #18168, PR #23249, PR #19466, PR #20284_

### graphql-ruby Conventions

- Use `resolver_method` (not `method`) when the resolver function is defined on the type class itself
- When a field delegates to a model method/association, use the `method:` option — don't define a redundant resolver method
- Omit `method:` when the field name matches the method name identically; for camelCase fields, `method:` maps to the snake_case Ruby method
- Define arguments with snake_case names — the framework auto-camelCases them for the schema
- Use the `value` parameter on enum values to encode domain values directly, eliminating manual mapping
- The GraphQL type class serves as the presentation layer — put field-level presentation logic there, not in separate presenters
- graphql-ruby freezes input objects — `dup` frozen inputs before passing to code that mutates hashes
- When refactoring methods off a model, grep for implicit GraphQL field resolution — graphql-ruby calls `object.method_name` when no explicit resolver is defined
- When exposing Ruby enum/value objects, explicitly serialize to a string or scalar — Ruby's default `#to_s` produces internal representations
- All new GraphQL mutation/type files must use `# typed: strict` — never `typed: false` or `typed: true`; enforce this as a hard rule in code review
- Every new or modified method must ship with a Sorbet `sig` block — this is a hard team standard, not best-effort
- Use the `GraphQL::` namespace (uppercase QL), not `Graphql::` — in Ruby they are different constants and mixing them risks accidental method overwrites in open modules
- Use the `object_type` class method on GraphQL type classes to declare the expected Ruby object type — provides Sorbet static type checking and catches type mismatches at compile time rather than runtime
- For BatchLoader-backed fields, use `BatchLoader::GraphQL` as the Sorbet return type — not `T.untyped`; check existing type files in the same module for the convention
- For mutation return hashes, use Sorbet typed shape syntax (`returns({ key: Type })`) rather than `T::Hash[Symbol, T.any(...)]` — it gives Sorbet per-key type information and matches codebase conventions
- Use `||=` with `T.let` for memoized instance variables: `@cached ||= T.let(nil, T.nilable(T::Boolean))`
- In filtering resolvers, ensure the narrowed scope is explicitly returned — Ruby's implicit return (last expression) can mask bugs when filtering logic is multi-line
- Add nil guards in resolvers for join columns that could be null even when "almost always" populated — silent nil propagation through GraphQL fields is harder to debug than an explicit filter; if a field truly should never be null, add a DB constraint instead

```ruby
# Bad — redundant resolver method
field :name, String, null: false
def name
  object.name
end

# Good — use method: option
field :name, String, null: false, method: :name

# Good — boolean with resolver_method
field :has_agreements, Boolean, null: false,
      resolver_method: :has_agreements?
def has_agreements?
  object.agreements.any?
end
```

_Sources: PR #20284, PR #23876, PR #17607, PR #18395, PR #18370, PR #22979, PR #19762, PR #26503, PR #23053, PR #23682, PR #22227, PR #22444, PR #25258, PR #25333, PR #25982, PR #22630, PR #26796, PR #26935, PR #26934, PR #6912, PR #5596, PR #6870_

### Mutation Design Patterns

- Follow `[resource][action]` naming convention (e.g., `bankingAttributionCreate`, not `createBankingAttribution`)
- Use keyword arguments in `perform` methods — not positional args, not `@inputs`
- Don't pass `current_user` as a mutation argument — use `context[:current_user]` on the backend
- For one-of-many dispatch, use an enum argument instead of multiple boolean flags
- When a mutation's precondition checks don't depend on input, expose them as a queryable boolean field (e.g., `canApprove`) for proactive frontend UX
- Data-modifying operations must be mutations, never queries
- When the codebase has an established command pattern for mutations, follow it for new types
- Avoid generic nested field names like `input` that produce `input: { input: { ... } }` at the call site — use domain-specific names (e.g., `form1065Input`)
- For mutations with multiple possible owner types, use a required polymorphic pair (enum type + ID) rather than multiple optional ID fields — makes the invariant structural
- Name mutations after the specific operation (`syncMembersToVenture`) — not vague prefixes like `fix`
- Include idempotency guards (`find_or_create_by`, upsert, or explicit existence checks) for mutations clients may retry on transient errors — double-submits and network retries are common in GraphQL clients
- Wrap multiple related DB writes in a transaction — a failure mid-mutation otherwise leaves data in an inconsistent state; this is critical in financial/payment contexts
- Use separate `CreateInputType` and `UpdateInputType` when Create and Update have different required fields — sharing a single input type forces all fields optional, pushing required-field validation into the mutation body instead of the service

```ruby
# Bad — positional args, generic naming
def perform(id, type, user_id)
  ...
end

# Good — keyword args, resource-first naming
# mutation: fundraisingCampaignUpdate
def perform(fundraising_campaign_id:, name:)
  ...
end
```

_Sources: PR #25493, PR #23640, PR #23936, PR #18370, PR #18582, PR #25216, PR #23508, PR #22526, PR #24028, PR #18332, PR #25798, PR #22470, PR #26502, PR #25593, PR #24089, PR #17167, PR #3696, PR #5518, PR #6774_

### Apollo Client Patterns

- Use the `loading` state from `useMutation` — don't duplicate with manual `useState`
- Always add explicit generic type parameters to `useQuery` and `useMutation` (e.g., `useQuery<MyQuery, MyQueryVariables>`)
- Use `useQuery` with `skip` option for deferred queries (e.g., modal open) instead of `useState` + `useLazyQuery`
- Avoid Apollo's `onCompleted` callback to sync query results into state — use `useEffect` on the data instead
- Never use `any` for GraphQL query results — use generated types from codegen
- Use shared hooks (`useMutationWithToast`) for mutation + feedback patterns before implementing custom logic
- When data comes from a query with multiple fragments on the same type, the result is an intersection (`&`), not a union (`|`)
- After auth-changing mutations (login, session refresh), use `fetchPolicy: 'network-only'` for follow-up queries — Apollo's cache reflects pre-auth state and won't invalidate automatically
- Don't pass fake objects to satisfy context provider type requirements — restructure the component or use the fragments pattern instead

```tsx
// Bad — manual loading state
const [loading, setLoading] = useState(false)
const [mutate] = useMutation(MUTATION)
const handleClick = async () => {
  setLoading(true)
  await mutate()
  setLoading(false)
}

// Good — use hook's loading
const [mutate, { loading }] = useMutation(MUTATION)
```

_Sources: PR #20299, PR #20929, PR #25970, PR #26508, PR #18370, PR #24492, PR #24911, PR #24870, PR #26447, PR #22105, PR #25982, PR #24921, PR #19686, PR #26320, PR #26368, PR #25351, PR #26557, PR #24173, PR #18148_

### Schema Field Naming

- Don't repeat the parent type name in field names (`distribution.amount`, not `distribution.distributionAmount`)
- Avoid naming fields `type` in polymorphic types — use `category`, `kind`, or the domain term
- Use fully qualified names over abbreviations in APIs (e.g., `fundraisingCampaign`, not `fc`)
- Follow consistent naming for analogous fields across types
- Expose relationships as typed objects or unions, not bare ID lists
- When structured data shares common fields (checkable, checked, label), use a dedicated type rather than scattering booleans

```graphql
# Bad — bare IDs, redundant naming
type Distribution {
  distributionAmount: Float
  relatedFundIds: [ID!]!
}

# Good — clean naming, typed relationships
type Distribution {
  amount: Int!
  relatedFunds: [Fund!]!
}
```

_Sources: PR #26113, PR #18179, PR #23892, PR #23787, PR #24068, PR #24028, PR #20656, PR #17749, PR #22470_

### Backend Logic Placement

- Keep permissions and state transition logic on the backend — expose pre-computed booleans (`canApprove`) rather than raw state data
- Push domain-specific conditional logic (entity type checks, special cases) into the backend presenter or resolver
- Compute display names and formatted labels in the GraphQL type, not on the frontend
- Perform data ordering at the SQL or resolver layer, not in frontend code
- Display-specific sorting belongs in the consuming resolver layer, not in the data-producing service

```ruby
# Bad — frontend computes permissions from raw data
# (frontend) const canApprove = data.transitions.includes('approve')

# Good — backend exposes computed boolean
field :can_approve, Boolean, null: false
def can_approve
  policy.can_approve?(object)
end
```

_Sources: PR #22511, PR #20656, PR #24830, PR #24427, PR #19527, PR #22824, PR #25730, PR #23696, PR #24820_

### Admin Resolver Authorization

- Inherit from base resolver/mutation classes (`Resolvers::Admin::BaseResolver`, `Mutations::Admin::BaseMutation`) that handle authorization — don't reimplement checks
- Admin types and resolvers live in a separate namespace; admin types may reference non-admin types but not vice versa
- Don't pass the current user as a mutation argument — use `context[:current_user]`; prefer method accessor over `@current_user`
- GraphQL enums and types should reference authoritative constants from the domain layer (packwerk), not duplicate values

_Sources: PR #22659, PR #24416, PR #22554, PR #22824, PR #25021, PR #18370_

### Avoid Circular and Over-Exposed Schema

- Be cautious about back-references that create circular query paths (child -> parent -> children) — they enable expensive or infinite queries
- Only expose fields the client actually needs — audit AI-generated types for unused fields before committing
- Prefer returning whole types and letting clients select fields, rather than creating specialized resolvers for individual fields
- Before adding a new field, check if it already exists on a more appropriate type
- GraphQL types should expose data unconditionally — don't encode frontend display logic in backend field visibility
- Don't prefetch presigned S3 URLs in GraphQL resolvers — URLs expire, waste bandwidth for unclicked rows, and add query complexity; return a controller route URL instead and generate the presigned URL on demand when the user actually requests it

```ruby
# Bad — circular reference enables expensive queries
# AdminInvestmentClosingType
field :fundraising_campaign, FundraisingCampaignType
# FundraisingCampaignType
field :investment_closings, [AdminInvestmentClosingType]

# Good — prop-drill specific fields or use a flat query
```

_Sources: PR #25594, PR #23750, PR #23787, PR #24231, PR #26447, PR #23640, PR #24056, PR #18566, PR #26503_

### @include/@skip Directive Placement

- Place `@include`/`@skip` directives on the field or fragment that wraps the resolver — not after the field where the resolver would still execute
- Incorrect placement causes auth-gated resolvers to fire for unauthenticated users even though the field is omitted from the response

```graphql
# Bad — resolver still executes for unauthenticated users
query PageQuery($includeAccount: Boolean!) {
  investAccount @include(if: $includeAccount) { ... }
}
# (directive positioned after the field in some implementations)

# Good — directive on the field prevents resolver execution
query PageQuery($includeAccount: Boolean!) {
  ... on Query @include(if: $includeAccount) {
    investAccount { ... }
  }
}
```

_Sources: PR #20449_

### Prefer GraphQL over REST for New Endpoints

- When the frontend already consumes a GraphQL API, add new data access through GraphQL mutations/queries rather than new REST controller actions
- Mixing API styles fragments the surface area and forces the frontend to maintain two different data-fetching patterns
- Controller endpoints often redirect to legacy pages and break the SPA experience — mutations keep the user in the React UI

_Sources: PR #23015, PR #25581, PR #24576_

### Boundary Input Validation

- Distinguish input validation (enforce at GraphQL boundary via types/schema) from state validation (enforce at runtime in commands/services)
- Don't duplicate validation in mutations when the model layer or GraphQL's strong typing already handles it
- When refactoring form inputs from strings to typed GraphQL arguments, audit all downstream consumers for stale string comparisons
- Don't perpetuate permissive nil-tolerance from legacy code into new mutations — enforce stricter validation at new entry points

```ruby
# Bad — redundant validation in mutation
def perform(status:)
  raise "invalid" unless %w[active inactive].include?(status)
  # GraphQL enum already prevents invalid values
end

# Good — trust the schema, validate state
def perform(status:)
  raise "already active" if record.active?  # state check
  record.update!(status:)
end
```

_Sources: PR #25493, PR #21670, PR #19326, PR #22756, PR #24601_

### Client-Side Data Fetching Boundaries

- When using client-only rendering boundaries (e.g., `ssr: false`), ensure data fetching is also inside the boundary — not just the render component
- Scope query refetches to specific events (post-mutation) — don't trigger refetches broadly on every render or update
- For frontend navigation URLs that follow a predictable pattern, define them in frontend path constants rather than plumbing through GraphQL

```tsx
// Bad — query outside SSR boundary, only render inside
const { data } = useQuery(HEAVY_QUERY)
return <ClientOnly><HeavyComponent data={data} /></ClientOnly>

// Good — query inside boundary
return <ClientOnly><HeavyComponentWithQuery /></ClientOnly>
```

_Sources: PR #22105, PR #26308, PR #25620_

### Preloaded Association Hygiene

- When associations are preloaded, use Ruby in-memory `select`/`reject`/`filter` — calling `.where` or scopes on a preloaded association bypasses the cache and hits the DB again
- Don't replace abstracted association methods (e.g., `events_out`) with direct AR queries — abstractions respect preloading
- Avoid dual access patterns (both `through` and direct) for the same association — makes preloading unpredictable
- When only checking existence across a has_many, collapse to a single `.where(...).exists?` query
- `includes` works with polymorphic `belongs_to` associations — the misconception that it doesn't is wrong; only `has_many :through` chains are blocked for polymorphic types

```ruby
# Bad — .where on preloaded association triggers new query
def active_members
  object.members.where(active: true)  # ignores preload
end

# Good — in-memory filter on preloaded data
def active_members
  object.members.select(&:active?)
end
```

_Sources: PR #20760, PR #21834, PR #22226, PR #19252, PR #24155, PR #25376, PR #22552_

### Generated TypeScript Types for GraphQL

- Always add explicit generic type parameters to `useQuery` and `useMutation` (e.g., `useQuery<MyQuery, MyQueryVariables>`)
- Never use `any` for GraphQL query results — use codegen-generated types
- Derive function parameter types from query results using indexed access types (e.g., `Query['field'][number]`) rather than manual interfaces
- Type component props to the query's response type, not the full schema type — schema types may include fields the query doesn't return

```tsx
// Bad — manual types, no codegen
const { data } = useQuery<any>(GET_USERS)
type User = { name: string; email: string }

// Good — generated types
const { data } = useQuery<GetUsersQuery, GetUsersQueryVariables>(GET_USERS)
type User = GetUsersQuery['users'][number]
```

_Sources: PR #20929, PR #25970, PR #19255, PR #19384, PR #26447, PR #24056, PR #19686, PR #25348_

### Shared Mutation Hooks and Utilities

- Before implementing mutation + toast/notification patterns, check for shared hooks like `useMutationWithToast`
- Before writing custom GraphQL error handling, check for utilities like `throwIfGraphQLError`
- Before bypassing a shared abstraction for a "complex" case, check if the hook supports customization (callbacks, overrides)
- Use Apollo's built-in `loading` state from `useMutation` instead of manual `useState` — avoids bugs from forgetting to reset in error paths

```tsx
// Bad — reimplementing existing patterns
const [mutate] = useMutation(MY_MUTATION)
const [loading, setLoading] = useState(false)
const handleSubmit = async () => {
  setLoading(true)
  try {
    const result = await mutate({ variables })
    toast.success('Saved!')
  } catch { toast.error('Failed') }
  finally { setLoading(false) }
}

// Good — use shared hook
const [mutate, { loading }] = useMutationWithToast(MY_MUTATION, {
  successMessage: 'Saved!',
})
```

_Sources: PR #24921, PR #24492, PR #26368, PR #26557, PR #24173, PR #18148, PR #20299, PR #24911_
