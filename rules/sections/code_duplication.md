---
scope: all
---

# Code Duplication

### Search for Existing Utilities Before Writing Inline Logic

- Before writing data transformations, date handling, string formatting, or entity creation, search for existing lib/service/utility functions.
- Common examples: `keyBy` for array-to-map, `pluralize` for labels, `startOfLocalDay` for dates, `libOrganization.entity.create` for records.
- Reusing shared utilities ensures consistent behavior and reduces maintenance surface.

```typescript
// Bad - manual reimplementation
const map: Record<string, Item> = {};
items.forEach((item) => { map[item.id] = item; });

// Good - use existing utility
const map = keyBy(items, 'id');
```

_Sources: PR #6348, PR #6541, PR #7243, PR #7184, PR #3062_

### Extract Duplicated Logic into Shared Helpers

- When the same logic appears in two or more places, extract it into a named helper immediately — do not wait.
- Applies to component init vs event handler paths, duplicated GraphQL queries across files, and repeated business logic in services.
- For GraphQL queries duplicated across components, extract into a shared custom hook.

```typescript
// Bad - same condition in init and handler
// in useEffect:
if (entities.length === 1) setSelected(entities[0].id);
// in onChange:
if (entities.length === 1) setSelected(entities[0].id);

// Good - named helper
const getAutoSelectEntityId = (entities: Entity[]) =>
  entities.length === 1 ? entities[0].id : undefined;
```

_Sources: PR #6710, PR #7047, PR #7076, PR #3062_

### Remove Redundant Wrapper Functions

- Delete wrapper functions that merely delegate to another function with the same signature.
- Avoid thin wrappers that add no logic, transformation, or abstraction — call the underlying function directly.
- When refactoring, check whether previously distinct functions have become identical and consolidate them.

_Sources: PR #6271, PR #6752_

### Deduplicate All Copies When Promoting to Shared

- When moving a local helper to a shared package (e.g., `std.ts`, `env.ts`), search the entire codebase for other local copies.
- Update all call sites to import from the single canonical location.
- Leftover local copies drift over time and defeat the purpose of the shared module.

_Sources: PR #6855_

### Keep Display and Filter Logic in Sync

- When modifying how a value is displayed or categorized, audit all related logic paths — filtering, sorting, and search.
- Display and filter logic often diverge silently when only one side is updated.

_Sources: PR #2947_

### Audit Copy-Paste Extractions for Leftover Artifacts

- When extracting shared components from existing code via copy-paste, audit the result for unused imports, variables, and dependencies.
- These artifacts were needed in the original context but not in the new shared location.

_Sources: PR #3070_
