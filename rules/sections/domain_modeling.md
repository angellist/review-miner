---
scope: all
---

# Domain Modeling

### Encode Invariants in the Schema, Not Implicit Conventions

- Store "current/head" pointers on the owning entity, not as boolean flags on child records — flags allow invalid multi-head states.
- Remove redundant fields from join tables when the relationship implies a single fixed role — they add complexity and can drift.
- Don't use null to encode semantic meaning (e.g., "null org ID means default"). Add an explicit boolean flag and enforce with a DB check constraint.

```prisma
// Bad — null implicitly means "default permission"
model EntityPermission {
  organizationId String?
  entityId       String?
}

// Good — explicit flag + DB constraint
model EntityPermission {
  organizationId String?
  entityId       String?
  isDefault      Boolean @default(false)
  // CHECK: !isDefault => organizationId IS NOT NULL AND entityId IS NOT NULL
}
```

_Sources: PR #3398, PR #3447, PR #3513_

### Place Attributes on the Entity That Owns Them

- Attach fields to the model that conceptually owns the data, not to a model that merely references it.
- Misplaced fields cause data consistency issues and confusing ownership boundaries.

```prisma
// Bad — accreditation on a directory entry
model DirectoryInvestor {
  accreditationStatus String?
}

// Good — accreditation on the LP profile that owns it
model LpProfile {
  accreditationStatus String?
}
```

_Sources: PR #3573_

### Name Fields by Domain Semantics, Not UI Labels

- Choose database column names based on what the data represents, not how the UI currently displays it.
- UI concepts diverge from data meaning over time — precise schema names prevent confusion.

```prisma
// Bad — "joined" is a UI display concept
joinedAt DateTime?

// Good — describes the actual domain event
connectedAt DateTime?
```

_Sources: PR #3573_

### Event Log Tables with Typed JSON Payloads

- Embed the type discriminant inside the JSON payload, not as a separate DB column — enables natural TypeScript discriminated union narrowing.
- Follow existing naming conventions for event models (e.g., `*Event`).

```typescript
// Discriminant inside JSON enables type narrowing
type ActivityData =
  | { type: "entity_linked"; entityId: string }
  | { type: "note_edited"; content: string }
  | { type: "file_added"; fileId: string };
```

_Sources: PR #3573_
