---
scope: backend
---

# Temporal Workflows

### Workflow ID Idempotency

- Use deterministic workflow IDs (e.g., `category:paymentTransferId`) as the idempotency key
- Do not implement custom deduplication with timestamp flags — "do work then set flag" is inherently racy under concurrent calls
- Temporal's workflow ID uniqueness constraint provides atomic, race-free deduplication out of the box

```ts
// Bad — racy timestamp-based dedup
if (lastSentAt < threshold) {
  await enqueueEmail(paymentId);
  await updateLastSentTimestamp(paymentId); // race: two calls enqueue before either updates
}

// Good — Temporal handles idempotency via workflow ID
await client.workflow.start(sendPaymentEmail, {
  workflowId: `send-email:${category}:${paymentTransferId}`,
  taskQueue: "emails",
  args: [paymentId],
});
```

_Sources: PR #6662, PR #6663_

### Worker Infrastructure: One Queue Per Machine

- Run each Temporal task queue on a separate machine (pod) with tuned resources
- Do not run all queues on every replica — it wastes resources and collapses under load
- Use a single parameterized `startWorker` entrypoint configured via ENV vars, not per-job worker methods
- Tune per queue: replica count, thread count, machine size

```ts
// Bad — all queues on every replica
startEmailWorker();
startFileWorker();
startSyncWorker();

// Good — one entrypoint, configured per deploy
startWorker({
  taskQueue: process.env.TEMPORAL_TASK_QUEUE,
  maxConcurrentActivities: Number(process.env.MAX_ACTIVITIES),
});
```

_Sources: PR #4623_

### Health Probes Must Match the Process

- Health probes must check a task queue that the process actually subscribes to
- Probing for a task queue owned by a different process creates false positives and masks failures
- When migrating workers between processes, update health checks to reference the correct queues

_Sources: PR #4631_

### Activity Return Types Must Be Serializable

- Temporal serializes activity return values across the activity-workflow boundary
- Do not return tuples or objects that rely on iterability or prototype methods — they break after serialization
- Use plain objects or tagged discriminated unions for activity results

```ts
// Bad — tuple breaks after Temporal serialization
return [error, result] as const;

// Good — plain object survives serialization
return { ok: true, data: result };
// or tagged union
return { tag: "success", data: result } as const;
```

_Sources: PR #5075_

### Environment Guards Target Production

- Place defensive guards in production (e.g., require explicit queue names) rather than restricting development
- Development environments need flexibility for debugging and forcing edge cases
- Do not add dev-only guards that block exceptional setups needed for testing

_Sources: PR #4735_

### Calculate Actual Backoff Duration

- When configuring exponential backoff retries, calculate the actual maximum wait time given retry count and initial interval
- Match retry parameters to the job's scheduling cadence — no point in a backoff exceeding the next scheduled run
- Use 10-12 retries instead of unbounded counts to keep total within a reasonable window

```ts
// Bad — doubling backoff with 30 retries = ~16 years max wait
{ initialInterval: "1m", backoffCoefficient: 2, maximumAttempts: 30 }

// Good — bounded to fit nightly schedule
{ initialInterval: "1m", backoffCoefficient: 2, maximumAttempts: 10 }
// Max wait: ~1024 minutes ≈ 17 hours
```

_Sources: PR #22942_

### Don't Create Activities for Inline Checks

- Don't create separate Temporal activities for simple checks that can be resolved with data already available in the workflow
- Extra activities add latency, complexity, and failure points without benefit when the data is at hand

_Sources: PR #24636_

### Prefer Temporal Over Sidekiq for Critical Work

- For event processing requiring guaranteed delivery and good observability, prefer Temporal over Sidekiq
- Sidekiq lacks delivery guarantees and its failure modes are hard to observe
- The `sidekiq_unique_jobs` gem has been a recurring source of incidents
- Reserve Sidekiq for fire-and-forget background work where occasional failures are acceptable

_Sources: PR #24857_

### Don't Use Exceptions for Expected Business Cases

- Don't raise RuntimeError for expected business edge cases that will occur in production
- Use structured logging (Sentry) or notifications (Slack) for cases needing human attention
- Reserve exceptions for truly unexpected failures

```ruby
# Bad — raises frequently in production
raise "Unrecognized transfer category: #{category}"

# Good — routes to human workflow
ErrorTracker.warn("Unrecognized transfer category", category: category)
SlackNotifier.send(channel: "#ops", message: "Unknown category: #{category}")
```

_Sources: PR #23830_

### Reload Associations After Creating Child Records

- After creating a record that belongs to an already-loaded association, Rails serves stale cached data
- Always reload the association or parent record before querying for the newly created child

```ruby
# Bad — association cache doesn't include new document
tax_return.documents.create!(attrs)
doc = tax_return.documents.find_by(type: "K1") # nil!

# Good — reload first
tax_return.documents.create!(attrs)
tax_return.documents.reload
doc = tax_return.documents.find_by(type: "K1")
```

_Sources: PR #21735_

### Stage Transitions Should Carry Context

- In state machine / workflow systems, stage transitions should carry the data changes that caused them
- This enables auditability (reconstruct state by replaying transitions) and supports reverting to previous states
- Don't strip context from transitions even if the data also lives on the parent record

_Sources: PR #26102_

### Audit Consumers When Expanding Polymorphic Types

- When expanding polymorphic associations to accept new types, audit all downstream consumers that use `is_a?` checks
- Hardcoded type checks silently fail for new types — extract shared methods that handle all supported types

```ruby
# Bad — breaks when ForeignTaxRep::Tracker is added
if target.is_a?(FlowthroughK1Tracker)
  target.corporation
end

# Good — handles all target types
def corporation(assignment_target)
  case assignment_target
  when FlowthroughK1Tracker then assignment_target.corporation
  when ForeignTaxRep::Tracker then assignment_target.corporation
  end
end
```

_Sources: PR #25668_

### Early Dispatch Over Scattered Type Checks

- When handling multiple object types in a service, prefer early dispatch to a polymorphic handler
- Don't scatter `is_a?` checks throughout — branch once at the entry point
- Check if an existing service already supports both types before adding conditional branches

_Sources: PR #19855_

### Place Reusable Logic in Service Objects

- When writing domain logic helpers in workflow or script files, consider whether the logic belongs in a service class
- Service objects make business logic discoverable, testable, and available to other callers

_Sources: PR #19156_

### Eliminate Leftover Two-Step Fetch Patterns

- Watch for two-step fetch patterns (fetch IDs then fetch records) left over from earlier designs
- If the intermediate ID list serves no purpose, collapse into a single query that returns records directly

_Sources: PR #26667_

### Audit Copied Workflow Code for Vestigial Logic

- When copy-pasting from another workflow, review whether all parts are needed — unused return values, parameters, and placeholder records add confusion
- Remove unused parameters from service interfaces, especially those added for manual/console workflows that now have UI alternatives
- Before propagating patterns like ignored/placeholder records, verify downstream consumers actually use them
- Use existing helper modules instead of duplicating workflow logic across classes

```ruby
# Bad — copy-pasted boolean return no caller uses
def execute
  do_work
  true  # vestigial from source workflow's retry logic
end

# Good — remove what the new context doesn't need
def execute
  do_work
end
```

_Sources: PR #17260, PR #20415, PR #21733, PR #24972_

### Avoid Temporal Qualifiers in Names

- Don't name classes, CSS identifiers, or feature flags with qualifiers like "Next", "New", "V2", or "refresh"
- Use descriptive names that reflect what distinguishes the thing (e.g., the underlying technology, year, or precise descriptor)
- "Eventually rename" tasks rarely happen — the qualifier becomes permanent confusion and creates collisions on the next iteration
- If versioning is unavoidable, append a year (e.g., `layout-shell-2026`) rather than a vague qualifier

```ruby
# Bad — becomes misleading once it's no longer "next"
class NextDealTermVerificationService; end
# layout-refresh CSS class — stale after the next refresh

# Good — describes what makes it distinct
class GeminiDealTermVerificationService; end
# layout-shell-2026
```

_Sources: PR #19812, PR #2539_
