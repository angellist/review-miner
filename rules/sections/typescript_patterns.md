---
scope: frontend
---

# Typescript Patterns

### Avoid Type Assertions — Use Narrowing, Validation, or Return Types

- Never use `as Type` to silence the compiler — investigate the underlying type mismatch instead.
- Use type narrowing (typeof, instanceof, discriminated unions) instead of `as any` or `as unknown`.
- Annotate function return types rather than casting at call sites.
- When a cast is truly unavoidable, extract the casted value into a named variable — never repeat the same cast.
- Prefer `as const satisfies Type` over `as Type` for const objects — it validates without losing narrowing.

```typescript
// Bad — cast hides mismatches
const config = getToastConfig() as NovaToastConfig;

// Good — return type annotation catches mismatches in the function body
function getToastConfig(): NovaToastConfig { ... }

// Bad — repeated cast
doA(response as Record<string, unknown>);
doB(response as Record<string, unknown>);

// Good — extract once
const parsed: Record<string, unknown> = response as Record<string, unknown>;
doA(parsed);
doB(parsed);
```

_Sources: PR #2868, PR #5204, PR #5464, PR #5489, PR #5485, PR #6240, PR #6302, PR #6877, PR #6977, PR #3062, PR #2667, PR #4194, PR #4889, PR #4910, PR #7002_

### Non-null Assertions: Throw Descriptive Errors Instead

- Never use `!` (non-null assertion) when a value could legitimately be absent.
- Add an explicit null check that throws a descriptive error.
- When possible, restructure code to extract the value earlier so it's provably non-null.

```typescript
// Bad — crashes with unhelpful "Cannot read property of undefined"
const id = account.externalId!;

// Good — debuggable failure
if (!account.externalId) {
  throw new Error("Missing external account ID");
}
const id = account.externalId;
```

_Sources: PR #5464, PR #6108, PR #3827_

### Runtime Validation Over Type Casting for External Data

- Use Zod schemas (or equivalent) to validate external API responses — never trust `as Type`.
- For JSON blobs from the backend, prefer proper GraphQL types or Zod parsing over raw casts.
- Derive TypeScript types from Zod schemas with `z.infer<typeof schema>` to keep types and validation in sync.
- Use `.refine()` over `z.union` with `z.literal("")` for required-field validation.
- In CLI/engbot scripts (compiled to JS), use Zod schemas for argument parsing — provides runtime defaults, constraints, and error messages where TypeScript types are erased.

```typescript
// Bad — no runtime safety
const data = response.json() as SendGridResponse;

// Good — validates shape at runtime
const RESPONSE_SCHEMA = z.object({ id: z.string(), status: z.string() });
const data = RESPONSE_SCHEMA.parse(await response.json());

// Derive form types from schema
type FormValues = z.infer<typeof formSchema>;
```

_Sources: PR #5495, PR #3055, PR #3407, PR #3696, PR #4421, PR #4187, PR #5644_

### Nullish Coalescing: Use ?? Not ||

- Always use `??` instead of `||` for null/undefined fallback — `||` treats `0`, `""`, and `false` as falsy.
- Never use truthiness checks on numeric fields — use `isNumber()` or explicit null checks.
- When a numeric field can be nullish, coalesce with `?? 0` before comparisons.
- Standardize on `undefined` over `null`, reserving `null` only at boundaries (DOM, React, GraphQL).

```typescript
// Bad — silently drops zero carry
const carry = investmentTerms?.totalCarry || undefined;

// Good — preserves zero as a valid value
const carry = isNumber(investmentTerms?.totalCarry)
  ? investmentTerms.totalCarry
  : undefined;

// Bad — 0 treated as "no fees"
if (details.managementFeesTotalPercent === 0) { ... }

// Good — null/undefined also treated as zero
if ((details.managementFeesTotalPercent ?? 0) === 0) { ... }
```

_Sources: PR #5485, PR #6774, PR #3284, PR #7093, PR #2868, PR #25883_

### Model Mutually Exclusive State with Discriminated Unions

- When exactly one of several fields must be present, use discriminated unions with a `kind`/`type` discriminant.
- Prefer discriminated unions over `never`-based XOR types — TypeScript narrows them more reliably.
- Don't introduce discriminated unions preemptively — start simple and add only when fields actually diverge.
- When a function branches into entirely separate code paths per variant, split into separate functions.

```typescript
// Bad — optional fields allow invalid combinations
type TransferArgs = { accountId?: string; inviteId?: string };

// Good — discriminated union enforces XOR
type TransferArgs =
  | { kind: "account"; accountId: string }
  | { kind: "invite"; inviteId: string };
```

_Sources: PR #5968, PR #6043, PR #6108, PR #6575_

### Optional vs Required: Let Types Enforce Invariants

- Make fields required when they should always be present — optional fields that are practically mandatory hide bugs.
- Prefer `prop: T | undefined` over `prop?: T` when the key must always exist but the value may be absent.
- When an auth guard guarantees a value exists, don't mark it optional in downstream signatures.
- Guard rendering upstream (conditional render while loading) rather than making child props nullable.

```typescript
// Bad — callers can silently omit categoryKey
interface EmailConfig { categoryKey?: string; }

// Good — TypeScript enforces every caller provides it
interface EmailConfig { categoryKey: string; }

// Bad — key can be omitted entirely
type Context = { balance?: BaseMoney };

// Good — key always present, value may be undefined
type Context = { balance: BaseMoney | undefined };
```

_Sources: PR #5558, PR #5565, PR #4762, PR #2690, PR #3462, PR #6808_

### Avoid TypeScript Enums — Use Const Objects or Zod

- Use `as const` arrays or const objects instead of TypeScript `enum` — enums generate runtime code incompatible with erasable syntax.
- When an existing enum/const exists for a value set, use it as the type annotation and for comparisons — never hardcode string literals.
- Use Prisma-generated enums for database fields instead of hardcoded strings.
- For new categorical values, define `as const` + matching GraphQL enum + Zod validation.
- Prefer typed string literals over raw strings for domain values.

```typescript
// Bad — TS enum generates runtime code
enum TransferType { DataRoom = "data-room" }

// Good — const + zod
const TRANSFER_TYPES = ["data-room", "direct"] as const;
const TransferTypeSchema = z.enum(TRANSFER_TYPES);
type TransferType = z.infer<typeof TransferTypeSchema>;

// Bad — hardcoded string and untyped param
if (status === "transferred") { ... }
function display(statusLabel: string) { ... }

// Good — use existing enum constant and type
if (status === PositionStatusLabels.Transferred) { ... }
function display(statusLabel: PositionStatusLabels) { ... }
```

_Sources: PR #6541, PR #3068, PR #4187, PR #3539, PR #23692_

### Derive Types From Source — Don't Duplicate

- Use `Pick<Type, "field1" | "field2">` for subsets of existing types — stays in sync automatically.
- For Prisma, define the `include` as a typed const, then derive the payload type via `Prisma.GetPayload`.
- Use `z.infer` to derive types from Zod schemas — never maintain a parallel manual type.
- Reserve `ReturnType<typeof fn>` for external libraries; write explicit return types for owned functions.
- Before defining a local type for a third-party resource, check if the library ships its own type — re-export from upstream instead of defining custom schemas that drift from the provider's source of truth.

```typescript
// Bad — manual type that can drift
type MemberInfo = { accountId: string; organizationId: string };

// Good — derived from source
type MemberInfo = Pick<OrganizationMember, "accountId" | "organizationId">;

// Prisma pattern
const includeRelations = { members: true, settings: true } satisfies Prisma.OrgInclude;
type OrgWithRelations = Prisma.OrgGetPayload<{ include: typeof includeRelations }>;

// Bad — custom Zod schema duplicating what the provider SDK already exports
const myCloudflareSchema = z.object({ zone: z.string(), ... });

// Good — re-export the upstream type
export type { CloudflareZone } from "@cloudflare/types";
```

_Sources: PR #3004, PR #5204, PR #3521, PR #4421, PR #3062, PR #218, PR #2546_

### Prefer Explicit Type Mapping Over Generic Transforms

- Write discrete type-to-type mapping functions instead of generic transform helpers that use `any`.
- When mapping arrays to known types, annotate the return type on `.map<T>()`.
- Create domain-specific state types rather than having consumers interpret raw underlying states.

```typescript
// Bad — generic snake-to-camel with `any`
function transform<T>(obj: Record<string, any>): T { ... }

// Good — explicit mapper with guaranteed types
function toOpportunityMember(raw: DataRoomMember): OpportunityMember {
  return { id: raw.id, name: raw.display_name };
}
```

_Sources: PR #5204, PR #3489, PR #4525_

### Function Signatures: Options Objects and Immutability

- When a function has 3+ optional parameters (especially of the same type), use a named options object.
- Prefer `const` with ternary/conditional expressions over `let` with reassignment.
- Don't use classes as function containers — use plain object exports when there's no instance state.
- Use `[value].flat()` to normalize single-item-or-array into a consistent array.

```typescript
// Bad — positional args are fragile
function listMembers(search?: string, state?: string, startDate?: string) {}

// Good — options object with domain types
function listMembers(opts: {
  search?: string;
  state?: MemberState[];
  startDate?: Date;
}) {}
```

_Sources: PR #5539, PR #6421, PR #3101, PR #4621, PR #4453_

### Type Guards and Filtering

- Use type-guard utilities like `isString` with `.filter()` instead of inline type checks.
- Use `as const satisfies readonly T[]` for constant tuples used in type narrowing.
- Write reusable `isOneOf` type guards for validating strings against known sets.
- `new Set()` does not deduplicate objects by value — use a Map keyed by unique property.
- When using `'prop' in obj` as a type discriminant, ensure all union members formally declare or explicitly omit the discriminating property — relying on implicit absence is fragile.
- Prefer an explicit truthiness guard (`obj &&`) over optional chaining (`obj?.prop`) when you need TypeScript to narrow the type for an entire expression — the guard narrows downstream access, eliminating the need for `?.`.

```typescript
// Bad — inline check, no narrowing
items.filter(x => typeof x === "string");

// Good — type guard narrows the result type
items.filter(isString);

// Bad — 'size' in item relies on implicit absence in SectionItem
if ('size' in item) { /* RowItem path */ }

// Good — discriminating property is formal in both union members
type RowItem = { size: InputSize; ... };
type SectionItem = { size?: never; ... };
```

_Sources: PR #6348, PR #7002, PR #6056, PR #5238, PR #2303, PR #20821_

### Lookup Tables: Encapsulate Access with Fallbacks

- When a const object is used as a lookup table with dynamic keys, use `Record<string, V>` to avoid cast proliferation.
- Prefer `Record<K, V>` for typed object maps over index signatures or type assertions — it's more idiomatic and expressive.
- Encapsulate lookups in a helper function with a fallback for missing keys.
- For 1:1 relationships, model as a single value — not a single-element array.

```typescript
// Bad — cast at every access site
const label = entityLabels[key as keyof typeof entityLabels];

// Good — Record type + helper with fallback
const entityLabels: Record<string, string> = { ... };
function entityTypeName(key: string): string {
  return entityLabels[key] ?? key;
}
```

_Sources: PR #4910, PR #6575, PR #18582_

### Prefer unknown Over any in Generic Containers

- Use `unknown` over `any` in generic containers and internal data structures.
- `unknown` with explicit `as T` confines unsafety to one visible point; `any` propagates silently.
- Avoid `Record<string, any>` even in test files — import the library's precise type (e.g., Prisma's `InputJsonValue`).

```typescript
// Bad — any propagates unchecked
const cache = new Map<number, any>();

// Good — unknown forces explicit cast at retrieval
const cache = new Map<number, unknown>();
const value = cache.get(id) as MyType;
```

_Sources: PR #6977, PR #3716, PR #5485_

### Keep Types and Tests in Sync

- When changing a TypeScript interface, update all test files that construct objects of that type.
- Don't ship unused exports speculatively — add them when they have a consumer.
- Remove redundant type annotations that TypeScript can infer — they add noise and go stale.
- Use TypeScript `private` keyword over JS `#private` fields for consistency with other access modifiers.

```typescript
// Bad — speculative export, no consumer
export const unusedHelper = () => {};

// Bad — redundant annotation on inferred callback
items.map((item: Item) => item.id);

// Good — let TS infer
items.map(item => item.id);
```

_Sources: PR #6240, PR #4699, PR #3706, PR #6808_

### Simplify Type Definitions

- Place union types on the property (`{ prop: A | null }`) rather than creating object unions (`{ prop: A } | { prop: null }`).
- Hoist common properties to a base type rather than duplicating them in each union variant.
- When modeling external API types you don't control, prefer loose types (string) over narrow enums to avoid runtime mismatches.

```typescript
// Bad — verbose object union
type Result = { contact: Contact } | { contact: null };

// Good — union on the property
type Result = { contact: Contact | null };
```

_Sources: PR #3681, PR #5473, PR #4872, PR #2808_

### Annotate Type Suppression Comments

- Always annotate `@ts-expect-error` and `@ts-ignore` with a brief explanation of the underlying type issue.
- This helps future developers understand whether the suppression is still necessary.

```typescript
// Bad
// @ts-expect-error
formErrors[field] = message;

// Good
// @ts-expect-error nested form errors aren't being set properly
formErrors[field] = message;
```

_Sources: PR #19253_

### Use as const for Constant Arrays Used as Type Sources

- When defining a constant array that doubles as both a runtime value and a type source (via `typeof arr[number]`), always use `as const` to prevent type widening.
- Combine with `satisfies` for both const narrowing and enum validation.

```typescript
// Bad — indexing produces wide `Instruments` type, can't catch missing values
const instruments: Instruments[] = ["equity", "debt"];

// Good — preserves tuple type, catches missing values at compile time
const instruments = ["equity", "debt"] as const satisfies readonly Instruments[];
type InstrumentType = typeof instruments[number]; // "equity" | "debt"
```

_Sources: PR #17082_

### Omit vs Exclude: Know Your Utility Types

- Use `Exclude<Union, Member>` to remove a member from a union type — never `Omit`, which operates on object keys.
- Use `|` to add members to a union — never `&` intersecting a string literal with a union.
- `Omit` on a union type produces an overly-permissive type (often `string & {}`) that disables TypeScript checking — the tell-tale sign is arbitrary strings passing type checks.
- `Omit<T, K>` does NOT enforce that K is a valid key of T — add a compile-time constraint (e.g., `Constrain<T, keyof T>`) when building public API types via `Omit`.
- When fixing a fundamentally broken type, audit all callsites first — previously-accepted values may now produce type errors, warranting a major version bump.

```typescript
// Bad — Omit on a union silently produces string & {}
type IntentProp = Omit<Intent, 'info'> & { intent?: 'default' };

// Good — Exclude removes union member, | adds new one
type IntentProp = Exclude<Intent, 'info'> | 'default';

// Bad — Omit doesn't validate the key exists
type Public = Omit<MyObj, 'renamedKey'>; // no compile error on stale key

// Good — constrain the key at the Omit call site
type Public = Omit<MyObj, Constrain<'renamedKey', keyof MyObj>>;
```

_Sources: PR #2576, PR #2613_
