---
scope: all
---

# Testing Patterns

### Colocate Test Files with Source

- Place test files next to the source file they test (e.g., `Component.test.tsx` beside `Component.tsx`)
- Do not use separate `__tests__` directories
- In monorepos, each package with tests needs its own test runner config file so lint-staged and similar tools resolve correctly

```
# Bad
src/components/Button.tsx
__tests__/components/Button.test.tsx

# Good
src/components/Button.tsx
src/components/Button.test.tsx
```

_Sources: PR #2874, PR #2729, PR #5075_

### Test Isolation for Parallelism

- Scope each test to unique data (distinct orgs, users, IDs) instead of forcing serial execution
- Randomize all IDs and unique fields in E2E seeders — hardcoded values cause collisions in parallel runs
- Use insert, not upsert, in seeders; upsert masks ID collision problems
- Never use `jest.setTimeout` or serial patterns to avoid shared-state conflicts

```typescript
// Bad — destroys parallel execution
jest.setTimeout(30000);
// relies on shared org across tests

// Good — each test gets its own org
const org = await createOrg({ handle: randomHandle() });
```

_Sources: PR #3642, PR #6808_

### Black-Box Testing over Mock Verification

- Assert on outputs and side effects, not on whether specific internal functions were called
- Mock-invocation assertions break when internals are refactored and don't prove correctness
- If mocking is necessary, validate the resulting output

```typescript
// Bad — coupled to implementation
expect(mockService.process).toHaveBeenCalledWith(input);

// Good — verifies actual behavior
const result = await handler(input);
expect(result.status).toBe("completed");
```

_Sources: PR #6108_

### Cover Edge Cases Explicitly

- When adding special-case handling (blank strings, null, zero), add matching test cases
- For filtered lists, always test the null/uncategorized variant
- For pagination, test boundary conditions: zero offset, zero limit, offset-by-one
- For regex, include false-positive inputs that superficially resemble the pattern
- For mutations, assert unchanged fields were not accidentally modified
- For services that operate on parallel/sibling entities, add a test for sequential calls — one sibling's operation can silently undo another's state changes if the resolution check is too narrow

```typescript
// Mutation test — verify no side effects on untouched fields
await editMember({ name: "New Name" });
const member = await getMember(id);
expect(member.name).toBe("New Name");
expect(member.role).toBe("admin"); // unchanged field preserved
```

_Sources: PR #5995, PR #3004, PR #3129, PR #2729, PR #3407, PR #18479_

### Derive Test Values from Source-of-Truth Constants

- Reference production constants and derive boundary values (e.g., `MAX + 1`)
- Do not hardcode magic numbers that duplicate business rules
- Inject explicit timestamps instead of using real delays for time-dependent tests

```typescript
// Bad
const overLimit = 500_001;

// Good
const overLimit = MAX_ACH_TRANSFER_AMOUNT_CENTS + 1;
```

_Sources: PR #6355, PR #6083_

### Use Generated GraphQL Mocks

- Use codegen-generated mock helpers (e.g., `mockEntity()` from `gen/graphql/mocks`) instead of hand-rolling test fixtures
- Generated mocks stay in sync with the schema automatically
- Check for existing generated mocks before writing manual ones

_Sources: PR #3244, PR #4980_

### mockClear vs mockReset

- Use `mockClear` to reset call counts between tests while preserving mock behavior
- Use `mockReset` only when you need to remove the mock implementation entirely
- Confusing the two causes tests to silently stop returning values

_Sources: PR #3243_

### E2E Fixture Architecture

- Fixtures provide reusable tools and integrations, not test-specific data configuration
- Test-specific setup belongs in the test files; promote to shared fixtures only when reused
- Use an OOP builder pattern with method chaining for complex domain relationships
- Place relationship methods on the proto that owns the relationship, internalizing dependency resolution
- Keep DB seeders off the public fixture API; use Symbol-keyed properties for internal sharing
- Refactor repetitive form-filling into loops over data structures

```typescript
// Builder pattern for fixtures
senderOrg
  .createDistribution({ amount: 1000 })
  .createPayment(directoryEntity);
```

_Sources: PR #6808, PR #7227, PR #7132_

### Exhaustive Classification Testing

- For mutually exclusive predicates, define a truth table mapping all inputs to expected outputs
- Assert true for the matching type and false for all others in a single loop
- This prevents false positives from untested combinations and scales as variants are added

```typescript
const expected: Record<TransferType, boolean> = {
  INTERNAL: true, OUTBOUND: false, INBOUND: false,
};
for (const [type, result] of Object.entries(expected)) {
  expect(isInternal(type)).toBe(result);
}
```

_Sources: PR #6083_

### E2E Infrastructure Safety

- Never hardcode fallback values for env vars in E2E infrastructure — require explicit presence and fail fast
- Comment all test-only code (date pinning, mock configs, feature flags) explaining the "why"
- Environment-gate load-testing scripts that send external communications (emails, SMS) to staging only
- When anonymizing production data for staging, preserve well-known email domains (gmail.com, hotmail.com, yahoo.com) rather than obfuscating them — systems that validate email domains will reject anonymized addresses, making staging data non-production-like

_Sources: PR #6855, PR #4217, PR #3940, PR #24683_

### Use Data Layer Abstractions in Tests

- Prefer data layer methods over raw ORM queries in tests
- The data layer handles parsing/casting (e.g., JSON settings) that you'd otherwise replicate manually
- Tests that use the same code path as production are more trustworthy

```typescript
// Bad — manual casting
const org = await prisma.organization.findUnique({ where: { id } });
const settings = JSON.parse(org.settings as string);

// Good — uses data layer
const org = await data.organization.findBy({ id });
// org.settings is already parsed
```

_Sources: PR #7068_

### Explicit Seeder Dependencies

- In dependency graph systems (test seeders, module systems), declare dependencies explicitly even if transitively included
- Prevents breakage if intermediate dependencies change
- Makes dependency relationships self-documenting

_Sources: PR #3330_

### Test Complex Dataloaders

- Dataloaders with composite keys, complex grouping, or authorization logic need at least a happy-path unit test
- Verify results return in the correct order matching original keys

_Sources: PR #5377_

### Delete Flaky Tests or Make Them Diagnosable

- Don't skip flaky tests indefinitely — either delete them or invest in fixing them
- Skipped tests accumulate as tech debt with no owner and give a false sense of coverage
- If keeping a flaky test, add diagnostic output (e.g., print backtraces on failure) so the root cause can be found

_Sources: PR #22190_

### Keep PRs Focused — Revert Unrelated Changes

- Revert auto-generated or unrelated file changes (schema caches, lockfiles, generated artifacts)
- Unrelated diffs obscure review, risk merge conflicts, and can mask accidental changes to shared files
- Never reference production IDs, secrets, or real user data in test specs or code comments

_Sources: PR #22558, PR #26526_

### Use FactoryBot Traits for Optional Associations

- Don't add eager associations to base factories — they create implicit dependencies and slow unrelated tests
- Use traits for optional associated records so each spec explicitly opts in to the setup it needs
- This keeps factories lightweight and test intent clear

```ruby
# Bad — every test creates an LLC
factory :fund do
  after(:create) { |f| create(:llc, fund: f) }
end

# Good — opt-in via trait
factory :fund do
  trait :with_llc do
    after(:create) { |f| create(:llc, fund: f) }
  end
end
```

_Sources: PR #19507_

### Sanitize Cell Values in Excel/CSV Exports

- Always sanitize cell values to prevent CSV injection attacks
- Prefix dangerous characters (`=`, `+`, `-`, `@`, tab, carriage return) with a single quote
- Extract a `sanitize_cell_value` helper and apply to all user-originated fields

_Sources: PR #25581_

### Respect Packwerk Module Boundaries

- Don't reference code from another package that violates packwerk boundaries
- Use public APIs, move logic to the appropriate package, or add explicit dependencies
- The `lib` directory should remain app-agnostic — domain model references don't belong there
- Adding to the packwerk todo file is acceptable only as a temporary measure with a concrete resolution plan

_Sources: PR #17494, PR #23179_

### Never Load Mock Modules in Production Code

- Don't reference or load mock/test modules in production code, even behind environment variable guards
- Test doubles should only exist in the test environment
- Leaking them into production creates confusion about code paths and risks accidentally enabling mocks

_Sources: PR #23128_

### Normalize Before Comparing, Don't Special-Case in Loops

- When comparing data structures with insignificant differences (zero-valued entries), normalize both inputs first
- A simple equality check after normalization is easier to understand, test, and maintain than special-case logic in comparison loops

```ruby
# Bad — special-case logic in comparison loop
schedule_a.each do |entry|
  match = schedule_b.find { |e| e.key == entry.key }
  next if match.nil? && entry.value.zero?
  ...
end

# Good — normalize then compare
norm_a = schedule_a.reject { |e| e.value.zero? }
norm_b = schedule_b.reject { |e| e.value.zero? }
norm_a == norm_b
```

_Sources: PR #18496_
