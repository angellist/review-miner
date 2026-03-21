# Review Rule Generation from Library Practices

## Goal

Select practices from the best practices library that work as automated code review rules, synthesize them into concise rules, and merge them into the target rules file incrementally.

## Input

- **Library dir**: Read all library files matching the target scope
- **Root rules file**: Cross-cutting rules maintained manually. Read this to avoid duplication.
- **Target file**: The rules file to update (specified in the task prompt)

## What Makes a Good Review Rule

Rules are read by AI during automated PR review. Good rules are:

1. **Mechanically checkable** — verifiable by looking at a code diff. "Use X instead of Y", "Always add Z when doing W", "Never do X without Y".
2. **Specific and actionable** — clear enough that an AI reviewer can spot violations in a PR.
3. **High signal** — patterns that actually appear in PRs regularly, not theoretical edge cases.

### What does NOT belong

- Architectural guidance ("use hexagonal architecture", "prefer composition over inheritance")
- Design principles ("keep components under 200 lines", "minimize state")
- Process rules ("review auto-generated migrations", "verify with stakeholders")
- Patterns requiring deep context ("understand locking strategies before modifying concurrent code")
- Infrastructure/deployment patterns
- Testing strategies

## Rule Format

Each `## {topic}` heading corresponds 1:1 with a `library/{topic}.yaml` file:

```markdown
# Automated Review Rules

## error_handling

- **Use typed error codes**: Return typed error codes, not generic exceptions.
- **Wrap external API calls**: Use try/catch with proper timeout handling around external calls.

## database_patterns

- **FOR UPDATE locking**: Only lock rows you'll actually modify; prefer optimistic concurrency.
```

Format rules:
- `## {topic}` section headings sorted alphabetically
- Each rule: `- **{practice_title}**: One or two concise sentences.`
- One or two sentences per rule — if it needs more, it's too context-dependent
- No code examples — keep rules terse

## Synthesis

Do NOT create a 1:1 mapping from practices to rules. Within each topic section:

- **Synthesize** related/overlapping practices into fewer condensed rules
- Use the most representative practice title as the rule key
- A good synthesis merges 2-3 closely related practices into 1 tighter rule
- Skip practices that don't add unique value beyond what other rules cover

Target: ~3:1 compression, and no more than 50 rules per file.

## Your Task

### Step 1: Read Inputs

1. Read the existing target rules file (if it exists) — parse section headings and `**{title}**` keys
2. Read all library files where `scope` matches the target scope
3. Read the root rules file to understand cross-cutting rules (for dedup)

### Step 2: Diff Against Library

- **New**: practice exists in library but has no rule → evaluate for addition
- **Removed**: rule exists but source practice(s) no longer in library → remove
- **Unchanged**: rule exists and source practice hasn't changed → keep as-is
- **Updated**: rule exists but source practice changed significantly → update

### Step 3: Select and Synthesize New Practices

For each topic with new practices:
1. Filter: is this a good automated review rule?
2. Synthesize: group related practices, merge into condensed rules.

Be aggressive in filtering — fewer high-signal rules > many diluted ones.

### Step 4: Write the Updated File

Write the file with all changes applied. Preserve existing rules verbatim where unchanged.

## Completion

Report:
- Rules kept unchanged: {N}
- Rules added: {N}
- Rules updated: {N}
- Rules removed: {N}
- New practices skipped (not suitable): {N}
