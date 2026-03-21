---
scope: all
---

# Code Style

### Prefer const With Declarative Filtering

- Use `const` over `let` — avoid forcing readers to trace mutation points
- Chain `.filter()` with named predicate functions instead of mutating intermediate variables

```ts
// Bad — reader must track where `results` is mutated
let results = allEntities;
if (statusFilter) {
  results = results.filter(e => e.status === statusFilter);
}

// Good — data flow is explicit
const matchesStatus = (e: Entity) => {
  if (selected === 'review') return e.alerts.length > 0;
  if (selected === 'ready') return e.alerts.length === 0;
  return true;
};

const matches = allEntities
  .filter(e => !search || e.name?.toLowerCase().includes(search))
  .filter(matchesStatus);
```

_Sources: PR #6212_

### Data Layer: Composition Over Hardcoded Includes

- Do not bind Prisma `include` or `select` clauses directly into data-layer query functions
- Let callers specify which relations to load, keeping the data layer generic and reusable

```ts
// Bad — couples query to one use case
function getEntity(id: string) {
  return prisma.entity.findUnique({
    where: { id },
    include: { alerts: true, documents: true },
  });
}

// Good — caller controls shape
function getEntity<T extends Prisma.EntityInclude>(
  id: string,
  include?: T,
) {
  return prisma.entity.findUnique({ where: { id }, include });
}
```

_Sources: PR #6211_
