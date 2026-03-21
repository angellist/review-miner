# Best Practices Mining - Library Synthesis

## Goal
Update the best practices library for a topic by selectively incorporating new validated insights while preserving existing high-quality content.

## Tech Stack Context

When writing practices, use terminology and patterns from our stack:
- **Rails**: concerns, service objects, Pundit policies, ActiveRecord, Sidekiq, Temporal
- **React**: hooks, memo, component composition, TypeScript generics
- **GraphQL**: graphql-ruby resolvers, batch loaders, schema types
- **Financial**: accreditation, fund lifecycle, monetary precision, regulatory compliance

## Input
- **Library file**: Current library content for this topic
- **Insights file**: All insights (filter by topic)
- **Threads file**: Original PR review threads for context
- **Codebase**: Live access to verify patterns and examples

## Your Task

### Step 1: Load Current Library Content

Read the current library file to understand the baseline.

Library structure:
```yaml
topic: pagination
scope: backend

practices:
  - title: "Cursor Pagination"
    content: |
      - Filter in SQL before LIMIT, not after fetch
      - Match cursor field with filter field

      ```ruby
      # Bad - post-fetch filtering breaks pagination
      results = Model.limit(100).to_a
      results.select! { |r| r.status == :active }

      # Good
      Model.where(status: :active).limit(100)
      ```
    sources: [52854, 52394]
```

**Preserve this baseline.** Your job is selective update, not full rewrite.

### Step 2: Load All Insights for This Topic

Read the insights file and filter to insights where `topic` matches your topic.

### Step 3: Load Original Threads for Context

For each insight, load the original thread from the threads file using `thread_id` to verify the insight accurately reflects the PR discussion.

### Step 4: Decide What to Update

**Preserve practices unrelated to new insights:**
- If an existing practice isn't touched by any new insight, **leave it unchanged**
- Don't rewrite for style or minor improvements

**Update existing practices** when new insights add examples, edge cases, or clarifications.

**Add new practices** only for genuinely distinct patterns — preferably backed by multiple insights.

**Filter aggressively:**
- Single-source insights → skip unless the pattern is fundamental and non-obvious
- Generic language knowledge (e.g., "use BigDecimal for money", "call super", "use fullmatch()") → skip; the reviewer AI already knows these
- Practices that belong in a different topic → skip
- When in doubt, don't add — better to have a lean library than a bloated one

### Step 5: Structure the Updated Library

**Practice content structure:**
1. **Rule bullets** - Actionable statements, one per bullet, imperative form
2. **One code example** - Shortest bad → good pair that illustrates the pattern (optional but recommended)

**Use our stack's idioms in examples:**
- Ruby/Rails examples for backend practices
- TypeScript/React examples for frontend practices
- GraphQL examples for schema practices

**Keep practices compact (target: 5-12 lines per content field):**
- Lead with 1-3 rule bullets — no introductory prose
- No rationale clauses ("...because this ensures...")
- ONE code example maximum — shortest bad → good pair
- Each practice should stand alone

**Update sources:**
- Add PR numbers from new insights that contributed
- Keep existing PR numbers for historical practices

### Step 6: Handle Edge Cases

**Contradictions:** Verify against codebase; update whichever side is wrong.

**Section growing beyond ~15 practices:** Look for merges or cuts.

**New topic (no existing practices):** Group related insights into cohesive practices. Set appropriate scope.

## Output Format

**Update the library file in place.** Keep the same structure:

```yaml
topic: pagination
scope: backend

practices:
  # Preserved practice (no changes)
  - title: "Cursor Pagination"
    content: |
      [Original content unchanged]
    sources: [52854, 52394]

  # Updated practice (new example added)
  - title: "Offset Pagination Pitfalls"
    content: |
      [Original content]

      [New example from recent insight]
    sources: [52854, 52394, 53100]  # Added new PR

  # New practice (from new insights)
  - title: "Pagination with Filtering"
    content: |
      [Content based on new insights]
    sources: [53101, 53102]
```

## Completion

Report: "Done. Updated library/{topic}.yaml. Preserved {N} practices, updated {M} practices, added {K} new practices. Total practices: {T}."
