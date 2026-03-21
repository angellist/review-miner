# Best Practices Mining - Insight Extraction

## Goal
Extract generalizable best practices insights from PR review comment threads.

## Tech Stack Context

This codebase spans multiple repositories:

**Venture (Rails backend):**
- Ruby on Rails monolith with concerns, service objects, Pundit policies
- Sidekiq for background jobs, Temporal for workflows
- GraphQL API layer (graphql-ruby)
- Financial domain: accreditation, fund lifecycle, investment management
- Database: PostgreSQL with large table migrations requiring care

**Nova (React frontend):**
- TypeScript React SPA with hooks, component composition
- State management patterns, GraphQL client (Apollo/urql)
- Financial UI: forms with monetary calculations, regulatory displays

**Shared patterns:**
- GraphQL schema conventions (N+1 prevention, resolver patterns, type coupling)
- Cross-service data consistency
- Financial correctness (rounding, currency, accreditation rules)

## Input
- **Batch input file**: Contains the full thread data for your batch (threads + batch info)

## Your Task

### Step 1: Load Thread Data

Read the batch input file — it contains the full thread data for your batch under the `threads` key.

Each thread contains:
- `thread_id` - Unique identifier
- `pr` - PR number
- `root` - Original review comment with author, body, file path, created_at
- `replies` - Follow-up comments in the conversation
- `has_suggestion_block` - Whether comment includes code suggestions
- `pr_author` - GitHub login of the PR author (the person receiving the feedback)

### Step 2: Analyze Each Thread

For each thread, determine if it contains a generalizable best practice insight.

**Look for threads where:**
- A reviewer identified a problem or improvement opportunity
- The problem reflects a recurring pattern or principle
- The lesson applies beyond this specific PR
- There's clear guidance on how to handle similar situations

**Recognize domain-specific patterns:**
- **Rails patterns**: concerns, service objects, Pundit policies, Sidekiq jobs, ActiveRecord gotchas
- **React patterns**: hooks, component composition, state management, memoization
- **GraphQL patterns**: resolver conventions, N+1 prevention, schema coupling, batch loading
- **Financial domain**: accreditation rules, fund lifecycle, investment validation, monetary calculations
- **Migration safety**: large table operations, backward compatibility, zero-downtime deploys
- **Auth/permissions**: Pundit policies, JWT handling, session management

**Skip threads that:**
- Feedback was not accepted — the PR author dismissed it ("doesn't apply", "intentional",
  "we prefer this approach") or there's no evidence it was acted on (no reply, no indication
  of a fix). Use `pr_author` to identify which commenter is the PR author vs. the reviewer.
- Are style nits without deeper rationale (pure formatting, naming preferences)
- Are typo fixes or trivial corrections
- Are specific to deprecated code or removed features
- Are one-off situational fixes with no broader applicability
- Have no clear resolution or actionable takeaway

### Step 3: Extract Insight Content

For threads with generalizable insights, capture:

**What was the problem?**
- What issue did the reviewer identify?
- What was wrong with the original approach?

**How was it fixed?**
- What change was made or suggested?
- What pattern or approach replaced the problematic code?

**What's the generalizable lesson?**
- Why is the new approach better?
- When should this pattern be applied?
- What principle does this illustrate?

**Verify against PR context:**
- Check file paths to understand the code context
- Look at whether code suggestions were provided
- Don't just rely on comment text - understand what the code does

**Format as free-form markdown:**
Write a cohesive narrative that captures the problem, fix, and lesson. Include relevant details like:
- Component context (if relevant)
- Code patterns involved
- Why the issue matters
- When the pattern applies

Keep it concise but complete (aim for 3-7 sentences).

### Step 4: Handle Edge Cases

**Multiple insights in one thread?**
- Rare, but if a thread discusses truly distinct patterns, create separate insights
- Usually one thread = one insight (or skip)

**Was the feedback accepted?**
- Use the `pr_author` field to identify the PR author in the replies
- Extract only if there's positive evidence the feedback was acknowledged:
  accepted ("good catch", "fixed", "updated"), applied suggestion, or
  another team member confirmed
- Skip if the PR author rejected or dismissed the feedback
- Skip if there's no response from the PR author and no sign the code was changed
- When ambiguous, skip — it's better to miss a valid insight than to codify rejected feedback

**Unclear or unresolved threads?**
- If the thread ends without clear resolution → skip
- If the lesson is ambiguous or debatable → skip (can always revisit)

**Component-specific patterns?**
- Include them! Scoping happens later in topic assignment
- Capture the context clearly (e.g., "In the accreditation service...")

**Frontend vs backend patterns?**
- Both are valuable! The thread's file path indicates which area of the codebase applies.

## Output Format

```yaml
batch_number: 1
total_batches: 5
processed: 20  # How many thread IDs were in this batch
insights_extracted: 12  # How many insights were extracted
skipped: 8  # How many threads were skipped

insights:
  # Example 1: Extracted insight (Rails backend)
  - thread_id: 2646229957
    pr: 52854
    content: |
      A paginated query applied status filtering after fetching rows, reducing
      the result count below the page limit. The cursor-based pagination then
      incorrectly signaled end-of-data.

      Fix: Move filtering into the SQL WHERE clause before applying LIMIT.

      Lesson: Always filter in SQL before LIMIT, not after fetch. Post-fetch filtering
      breaks pagination assumptions and causes silent data loss.

  # Example 2: Extracted insight (React frontend)
  - thread_id: 2650123456
    pr: 53001
    content: |
      React component re-rendered on every parent update despite unchanged props,
      causing performance issues in large lists.

      Fix: Wrapped component with React.memo() and added custom comparison function
      for complex prop objects.

      Lesson: Use React.memo for expensive components in lists or frequently updated
      contexts. Provide custom comparator for object/array props to avoid false
      re-renders.

  # Example 3: Extracted insight (GraphQL)
  - thread_id: 2650200000
    pr: 53010
    content: |
      GraphQL resolver loaded associated records inside a field resolver, causing
      N+1 queries when the parent list had many items.

      Fix: Used batch loader (graphql-batch or dataloader) to coalesce queries.

      Lesson: Never load associations inside field resolvers without batch loading.
      Use the project's batch loader pattern for any resolver that touches the DB.

  # Example 4: Skipped thread (include pr for provenance)
  - thread_id: 2646230000
    pr: 52855
    skipped: true
    reason: "Style nit about variable naming without architectural rationale"

  # ... more insights and skipped threads
```

## Rules

**Focus on generalizable patterns:**
- Architectural decisions, not implementation details
- Principles that apply across multiple situations
- Patterns that reviewers want to see consistently followed

**Both codebases are valuable:**
- Backend patterns (Rails, GraphQL, Sidekiq, Temporal)
- Frontend patterns (React, TypeScript, Apollo)
- The thread's file path indicates which area applies
- Module-specific patterns are OK

**Verify, don't assume:**
- Use file paths to understand context
- Don't extract insights from comment text alone

**When in doubt, skip:**
- It's better to miss a marginal insight than extract noise
- Ambiguous or unresolved threads should be skipped
- One-off fixes without clear principles should be skipped
- Unacknowledged feedback should be skipped

**Be concise but complete:**
- Capture enough context to understand the pattern
- Include the "why" not just the "what"
- Keep it readable (avoid walls of text)

## Completion

Report: "Done. Batch {batch_number}/{total_batches} complete. Extracted {N} insights, skipped {M} threads. Output written to {output_file}."
