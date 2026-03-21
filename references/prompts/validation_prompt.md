# Best Practices Mining - Insight Validation

## Goal
Validate extracted insights against the current codebase to ensure they remain relevant and accurate.

## Repository Context

Validate against these repository roots:
- **Venture (Rails)**: Check for Rails patterns, service objects, GraphQL resolvers, migrations
- **Nova (React)**: Check for React components, hooks, TypeScript patterns, GraphQL client code

## Input
- **Insights file**: All extracted insights with status
- **Batch input**: Insight IDs to validate for this batch
- **Batch info**: Batch number and total batches
- **Codebase**: Live access to verify patterns, files, and code

## Your Task

### Step 1: Load Insights to Validate

Read the batch input file to get the insight IDs you need to validate. Then load the corresponding insights from the insights file.

Each insight contains:
- `id` - Unique identifier (e.g., "ext_2646229957_0")
- `thread_id` - Source PR review thread
- `pr` - PR number where pattern was discussed
- `status` - Should be "pending" for validation
- `content` - The insight narrative (problem, fix, lesson)
- `topic` - Will be null at this stage

### Step 2: Validate Each Insight

For each insight, verify it against the current codebase to determine if it remains valid and relevant.

**Validation criteria:**

1. **Pattern still exists?**
   - Does the pattern or code structure mentioned still exist?
   - Use Grep and Glob tools to search for relevant patterns
   - Check if the architectural approach is still used

2. **Referenced files/modules still present?**
   - Are the files, modules, or components referenced still in the codebase?
   - Check file paths mentioned in the insight
   - Verify component names and file paths are current

3. **Not about deprecated/removed features?**
   - Is the insight about APIs or patterns that have been removed?
   - Check for deprecation notices or removal commits
   - Look for migration guides suggesting the pattern is obsolete

4. **Still architecturally sound?**
   - Does the lesson align with current best practices?
   - Has the codebase evolved in ways that invalidate the insight?
   - Would following this advice still be correct today?

**Default to valid:**
- Only report rejections when you have clear evidence the insight is no longer relevant
- If unsure but the pattern seems reasonable, let it pass validation
- Missing exact code examples doesn't invalidate a principle-based insight

**Search strategies:**
- Use Grep to find pattern usage across the codebase
- Use Glob to verify file and directory structures
- Read key files to understand current implementations
- Check git history if needed to understand what changed

### Step 3: Document Rejections Only

For insights that fail validation, record why they should be rejected.

**Good rejection reasons:**
- "Referenced API was removed in PR #53000"
- "Module 'xyz_service' no longer exists, migrated to 'abc_service' in PR #54123"
- "Pattern deprecated: codebase now uses different approach (see module/README.md)"
- "Referenced file path no longer exists in the codebase"

**Not good rejection reasons:**
- "Code style has changed" (unless the insight is purely about style)
- "Better pattern exists" (the insight can still be valid even if not optimal)
- "Can't find exact code example" (principles matter more than exact examples)
- "Module seems inactive" (low activity doesn't mean pattern is invalid)

### Step 4: Handle Edge Cases

**Insight mentions specific code that changed?**
- If the principle still applies but the example is outdated → let it pass
- Only reject if the core lesson is invalidated

**Insight about a specific module you can't verify?**
- Do reasonable due diligence (check if module exists, search for patterns)
- If module exists and nothing suggests the pattern changed → let it pass

**Insight seems outdated but you're not certain?**
- Default to valid unless you have clear evidence
- Better to have marginal insights reach topic assignment than reject good ones

**Frontend vs backend patterns?**
- Validate against the area of the codebase indicated by the thread's file path.

## Output Format

**Only include rejections. Valid insights are not listed.**

```yaml
batch_number: 1
rejections:
  # Example 1: API removed
  - insight_id: ext_2646230001_0
    reason: "API PostFetchFilterer was removed in PR #53000, replaced with SQL-based filtering"

  # Example 2: Module no longer exists
  - insight_id: ext_2646230005_0
    reason: "Service 'legacy_auth' removed in PR #52800, migrated to auth_service"

  # If no rejections in batch, output empty list
  # rejections: []
```

## Rules

**Assume valid by default:**
- Only reject with clear evidence the insight is outdated or wrong
- Marginal cases should pass validation
- Principles are more important than specific code examples

**Verify against the codebase:**
- Don't rely on memory or assumptions
- Use Grep/Glob to search for patterns and files
- Read actual code to understand current state

**Be specific in rejection reasons:**
- Cite the PR number where something was removed/changed (if known)
- Reference specific files or modules that don't exist
- Explain what replaced the old pattern (if applicable)

**Don't reject for style preferences:**
- If the insight is about a principle that remains valid, keep it
- Better patterns existing elsewhere doesn't invalidate this one
- Focus on correctness, not optimization

## Completion

Report: "Done. Batch {batch_number}/{total_batches} complete. Found {N} rejections. Output written to {output_file}."
