---
scope: all
---

# Logging Observability

### Don't Report Expected Conditions as Errors

- If a code path handles a known/expected state, log at info/debug level — don't send it to the error tracker
- Noisy error trackers erode trust and make real issues harder to spot
- Reserve error reporting for genuinely unexpected failures

```ruby
# Bad — expected state triggers error tracker
if document.state == :archived
  Sentry.capture_message("Document is archived")
  return
end

# Good — log expected case, report only unexpected ones
if document.state == :archived
  Rails.logger.info("Skipping archived document #{document.id}")
  return
end
```

_Sources: PR #17138_

### Consistent Datadog Metric Tags

- When emitting Datadog metrics, check existing usages of the same metric name to ensure consistent tagging
- Missing tags on some emission sites creates blind spots in dashboards and monitors
- All emission sites for the same metric should use the same tag set

_Sources: PR #26769_

### Command/Audit Trail Pattern

- Structure service entry points so the public API creates a command (auditable record), and the command delegates to internal logic
- Place internal logic in a separate namespace (e.g., `Commands::ServiceName`) to prevent bypassing audit trails
- This enables future enforcement via module boundary tools like packwerk

```ruby
# Bad — internal logic called directly, no audit trail
Transfers::Logic.execute(params)

# Good — public API creates command, command calls internal logic
Transfers::Service.execute(params)  # creates Command record
# -> Command#apply calls Transfers::Logic internally
```

_Sources: PR #25117_

### Never Expose Sequential IDs Externally

- Don't expose auto-incrementing database IDs in external-facing exports or APIs
- Sequential IDs enable enumeration attacks and leak internal growth metrics
- Use slugs, UUIDs, or other opaque identifiers instead

_Sources: PR #17942_

### Logging Helpers Encapsulate Their Own Guards

- Move guard conditions inside logging helper methods rather than duplicating them at every call site
- Call sites should not need to check `if from != to` before calling `log_dimension_change` — the method handles that itself

```ruby
# Bad — guard duplicated at every call site
log_dimension_change(dc, key, from, to) if from != to

# Good — guard lives inside the helper
def log_dimension_change(dc, key, from, to)
  return if from == to
  # ... log the change
end
log_dimension_change(dc, key, from, to)
```

_Sources: PR #24247_

### Health Check Validation Semantics

- For existence-style health checks ("does a valid document exist?"), prefer "any pass" over "all must pass" semantics
- Strict "all must pass" logic produces false negatives when multiple versions of a record coexist (e.g., draft + executed)
- Match the check's logic to a human reviewer's mental model of what "healthy" means

```ruby
# Bad — fails if ANY document is not executed (too strict)
documents.all? { |doc| doc.executed? }

# Good — passes if ANY document is executed
documents.any? { |doc| doc.executed? }
```

_Sources: PR #20133_
