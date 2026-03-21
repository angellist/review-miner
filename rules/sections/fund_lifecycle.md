---
scope: fullstack
---

# Fund Lifecycle

### Entity Type-Aware Calculations and UI

- Branch logic by entity type (company vs fund) when computing metrics — a single code path that ignores the distinction silently produces wrong results
- Gate fund-type-specific UI behind explicit type checks (e.g., check for a connected venture vehicle before rendering BT-only components)

```ruby
# Bad - ignores entity type
check = opportunity.average_check

# Good - branch by type
check = if opportunity.fund?
          opportunity.average_vfund_check
        else
          opportunity.startup_check
        end
```

_Sources: PR #5357, PR #3397_

### Scope Queries to Vehicle Entities

- On the GP side, query vehicle entities specifically — not all OrganizationEntity records
- "Regular" (non-vehicle) entities are a legacy construct kept for edge cases (non-vehicle-backed templates, management company permissions) and should not appear in broad queries
- Overly broad entity queries pull in legacy data that causes confusion and incorrect behavior

_Sources: PR #5553_

### Snapshot Policy Config at Creation Time

- Every domain instance (e.g., transfer control) should go through the same policy path — even ad-hoc overrides create a policy+instance pair
- Snapshot policy settings into each instance at creation rather than referencing the live policy
- This gives each instance an accurate audit trail independent of future template changes

```ruby
# Bad - reference mutable policy
control.policy_id = policy.id
# control reads policy.rules at decision time — stale if policy changes

# Good - snapshot at creation
control.rules = policy.rules.deep_dup
control.policy_snapshot_id = policy.id
```

_Sources: PR #6257_

### Archive Over Hard Delete for Domain Records

- Prefer archiving over hard deletion for records with historical value (matches, transactions, audit-relevant data)
- When soft deletes add too much query complexity (deleted_at checks on every query), move records to an archive table instead

```ruby
# Bad - hard delete loses history
OpportunityMatch.where(opportunity_id: id).delete_all

# Good - archive then delete
OpportunityMatch.archive_for_opportunity!(id)
```

_Sources: PR #5309_

### Consistent Fund-Scoping Filters

- When implementing fund-scoping filters, check existing services (especially filing obligation service) for the canonical exclusion logic
- Fund lifecycle states — offboarding, jurisdiction — should be handled consistently across services
- Include offboarding checks (`transitioned_off_platform_at`, `tax_offboarded_at`) so flags eventually expire

_Sources: PR #20333_

### Avoid Overloading Domain Terms

- Don't overload domain terms that already have specific meanings in the codebase (e.g., "closing" can mean investment closing, fund closing, or campaign closing)
- Use precise technical terms for service and class names, not product marketing wrappers
- Choose domain-specific names (`FundLps` vs `RollingFundLps`) over implementation-detail names (`closing based` vs `subscription based`)

_Sources: PR #23427, PR #21856, PR #25513_

### Place GraphQL Fields on the Owning Type

- Place computed GraphQL fields on the type that owns the underlying data, not on a parent type
- This keeps the schema cohesive and lets consumers query naturally through the object graph

```graphql
# Bad — parent-level accessor
type RollingFund { investableCapital: Money }

# Good — on the segment that owns the data
type RollingFundCampaignSegment { investableCapital: Money }
```

_Sources: PR #25982_

### Snapshot vs Live Computation for Dual-Purpose Views

- When views serve dual purposes (preview of pending action AND historical log of completed action), consider whether computed fields remain accurate after execution
- If underlying state changes post-execution, either snapshot values at execution time or suppress stale computation

_Sources: PR #17961_

### Search Entire Codebase When Renaming

- When renaming features or routes, search the entire codebase for references to the old name
- Navigation links, breadcrumbs, view partials, and route helpers are easy to miss
- A systematic find-and-replace across all layers prevents stale references

_Sources: PR #17923_

### Follow Return-Type Naming Conventions

- In this codebase, `x_by_y` implies a hash/dictionary keyed by `y` — don't use it for scalar returns
- Methods returning a single value should use names that reflect the return type

```ruby
# Bad — reads like a hash lookup
def investor_count_by_subscription_id(sub_id)
  investors.where(subscription_id: sub_id).distinct.count
end

# Good — clearly returns a scalar
def unique_investor_count(sub_id)
  investors.where(subscription_id: sub_id).distinct.count
end
```

_Sources: PR #22152_
