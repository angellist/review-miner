# Best Practices Mining - Topic Assignment

## Goal
Assign topics to validated insights to enable organized synthesis into the best practices library.

## Domain Topic Taxonomy

Canonical topics for this codebase (use these exact names when applicable):

**Financial domain:**
- `financial_correctness` — monetary calculations, rounding, currency handling
- `accreditation_compliance` — investor verification, regulatory rules
- `fund_lifecycle` — fund creation, closing, subscription management

**Architecture:**
- `graphql_schema` — type coupling, resolver patterns, N+1, batch loading
- `migration_safety` — large table operations, backward compatibility, zero-downtime
- `auth_permissions` — Pundit policies, JWT handling, session management
- `data_integrity` — validation, atomicity, race conditions, locking

**Backend (Rails):**
- `rails_patterns` — concerns, service objects, ActiveRecord conventions
- `sidekiq_jobs` — background job patterns, retries, idempotency
- `temporal_workflows` — workflow patterns, activity design, state management

**Frontend (React):**
- `react_components` — component composition, memoization, rendering
- `react_state` — state management, hooks, context patterns
- `typescript_patterns` — type safety, generics, discriminated unions

**Cross-cutting:**
- `error_handling` — error types, recovery, logging
- `testing_patterns` — test design, fixtures, mocking
- `performance` — query optimization, caching, lazy loading
- `api_design` — REST/GraphQL conventions, versioning, contracts

You may propose new topics with `__new__:topic_name` if none of the above fit.

## Input
- **Insights file**: All insights with their validation status
- **Batch input file**: Contains the `insight_ids` you should process
- **Existing topics**: Provided in the task prompt — use these exact names when assigning to existing topics
- **Library directory**: Existing topic files (*.yaml) for deeper context
- **Codebase**: Access to understand patterns and verify context

## Your Task

### Step 1: Load Validated Insights

Read the batch input file to get your `insight_ids`, then look up those insights in the insights file.

### Step 2: Load Existing Topics

Check the library directory to see what topics already exist. Each `{topic}.yaml` file represents an established category.

### Step 3: Analyze and Group Insights

Read through all pending insights and identify patterns:

**Look for insights that:**
- Address the same architectural concern (e.g., pagination, error handling)
- Apply similar principles or patterns
- Relate to the same component or system (e.g., GraphQL, database queries)
- Share a common problem domain

**Consider scope:**
- Frontend vs backend insights should typically be separate topics
- Module-specific patterns may warrant their own topic if substantial
- Cross-cutting concerns (logging, testing) apply broadly

### Step 4: Assign Topics

For each insight, decide whether to assign it to an existing topic or propose a new one.

**Assign to existing topic if:**
- The insight fits naturally into an established category
- The lesson complements or extends existing practices
- The scope matches (frontend/backend/module)

**Propose new topic if:**
- The insight addresses a genuinely new concern not covered by existing topics
- There are multiple pending insights about this new topic
- The insight represents a distinct architectural area

**Topic naming guidelines:**
- Use descriptive, lowercase names with underscores (e.g., `cursor_pagination`, `error_handling`)
- Keep names concise but clear (2-3 words max)
- Prefer the canonical topics listed above when applicable

**New topic format:**
When proposing a new topic, use: `__new__:topic_name`

### Step 5: Handle Edge Cases

**Insight seems to span multiple topics?**
- Choose the primary topic that best captures the core lesson
- One insight should have one topic

**Uncertain between existing topics?**
- Choose the more specific topic if the insight is narrow
- Default to existing topic to avoid fragmentation

**Very few insights in new topic?**
- Be conservative: prefer existing topics over creating new ones
- Only create new topics if multiple insights justify it OR the pattern is fundamental

## Output Format

```yaml
assignments:
  - insight_id: ext_2646229957_0
    topic: financial_correctness

  - insight_id: ext_2646230002_0
    topic: error_handling

  - insight_id: ext_2647000000_0
    topic: __new__:feature_flags

  # ... all validated insights get assigned
```

**Requirements:**
- Every validated insight pending topic must get an assignment
- Use exact insight IDs from insights.yaml
- Use exact topic names from existing library files (case-sensitive)
- Use `__new__:name` format for new topics only

## Rules

**Prefer existing topics:**
- Avoid fragmenting the library with too many narrow topics
- Check if an existing topic could accommodate the insight

**Prefer canonical topics:**
- Use the domain topic taxonomy above when the insight fits

**Consider scope and applicability:**
- Frontend and backend patterns typically need separate topics
- Module-specific topics are OK if patterns are substantial

**Group related insights together:**
- Multiple insights about similar patterns should get the same topic
- Review all pending insights before assigning to identify patterns

## Completion

Report: "Done. Assigned topics to {N} validated insights. Created {M} new topics. Output written to {output_file}."
