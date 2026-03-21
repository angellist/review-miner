---
name: pr-review
description: "Review local changes before pushing using AngelList's mined PR review rules. Find issues, fix them, then re-review until clean."
---

# PR Review

You are reviewing the user's local changes using review rules mined from thousands of prior PR reviews.

## Step 1: Generate the review prompt

Run the review script against local changes:

```bash
python3 scripts/review.py --local -o tmp/review_prompt.md
```

If the user specified a different base branch (e.g., `develop`), pass it:

```bash
python3 scripts/review.py --local --base origin/develop -o tmp/review_prompt.md
```

If the user provided a PR URL or number instead, use that:

```bash
python3 scripts/review.py <PR_URL> -o tmp/review_prompt.md
```

## Step 2: Read and execute the review

Read the generated prompt file:

```
Read tmp/review_prompt.md
```

The prompt contains:
- The diff of all changes
- Relevant review rules (auto-selected based on changed file types/paths)
- Instructions for how to review

Follow the review instructions in the prompt. For each issue found, report:
- **File and line**
- **Problem** — concise description
- **Rule** — which mined rule it violates (if applicable)
- **Fix** — suggested code change

## Step 3: Fix issues

After reporting issues, fix them directly in the code. For each fix:
1. Edit the file to resolve the issue
2. Briefly note what you changed

## Step 4: Re-review

After fixes, re-run the review to confirm everything is clean:

```bash
python3 scripts/review.py --local -o tmp/review_prompt.md
```

Read the updated prompt and verify no remaining issues. Repeat Steps 2-4 until the review is clean.

## Notes

- Do NOT flag style nits or issues already caught by linters
- Focus on bugs, correctness, security, and rule violations
- Call out positive patterns too — good code deserves recognition
- If `rules/sections/` is empty, tell the user to run the mining pipeline first
