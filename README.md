# AL PR Review

Forked from [mine-best-practices](https://github.com/valon-technologies/mine-best-practices) by Valon Technologies — a Claude Code skill that extracts engineering best practices from PR review history.

This fork extends the mining pipeline with an automated review bot, GitHub Actions CI integration, and a Claude Code `/pr-review` skill for reviewing local changes before pushing.

Rules are **pre-mined and shipped in this repo** — you can start reviewing immediately without running the pipeline.

### What's mined

| Repo | PRs | Review Threads | Insights Synthesized |
|------|-----|---------------|---------------------|
| Venture | 3,542 | 9,825 | 1,808 |
| Nova | 1,849 | 5,166 | 874 |
| Treasury | 649 | 1,562 | 229 |
| Adapt | 222 | 553 | 96 |
| Ipseity | 69 | 161 | 30 |
| Infra | 128 | 299 | 45 |
| **Total** | **6,459** | **17,566** | **3,082** |

After filtering, **2,946 insights** are synthesized into practices across **35 rule sections** in `rules/sections/`. The raw data (threads, insights, library) is committed in `code_insights/`.

## Quick Start

```bash
# 1. Clone and install
git clone git@github.com:angellist/review-miner.git
cd review-miner
pip install -e .

# 2. Copy config (only needed for mining or bot — not for /pr-review)
cp config.yaml.example config.yaml
```

## Using with Claude Code (`/pr-review`)

The fastest way to use this. Run `/pr-review` from Claude Code inside any repo you're working on — it reviews your local changes against the mined rules before you push.

### Setup

The `/pr-review` skill needs to be accessible from the repo you're reviewing. Add this to the target repo's `.claude/settings.json`:

```json
{
  "skills": [
    "/path/to/al-pr-review/.claude/skills/pr-review"
  ]
}
```

Or symlink it:

```bash
# From your target repo (e.g. nova, venture)
mkdir -p .claude/skills
ln -s /path/to/al-pr-review/.claude/skills/pr-review .claude/skills/pr-review
```

### Usage

```bash
# In Claude Code, from your working repo:
/pr-review
```

This will:
1. Diff your local changes and auto-select relevant rules by file type/path
2. Review against the mined best practices
3. Fix any issues found
4. Re-review until clean

No `ANTHROPIC_API_KEY` needed — it runs through Claude Code's own session.

## Setting Up GitHub Actions (Automated CI Reviews)

> **Note:** The bot and GitHub Actions workflow are built but **not yet enabled** on any repo. The instructions below are for when we're ready to turn it on.

The repo includes a reusable workflow that reviews PRs automatically when they're opened. It only posts **critical** severity comments to keep noise low.

### 1. Add the `ANTHROPIC_API_KEY` secret

In your target repo's GitHub settings, add `ANTHROPIC_API_KEY` as a repository secret.

### 2. Create a caller workflow

In your target repo (e.g. `angellist/nova`), create `.github/workflows/pr-review.yml`:

```yaml
name: PR Review

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    uses: angellist/review-miner/.github/workflows/pr-review.yml@main
    with:
      repo_name: nova  # Must match a repo name in al-pr-review's config.yaml
    secrets:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

That's it. The bot will review every non-draft PR and post inline comments for critical issues.

### Severity filtering

The CI workflow defaults to `--min-severity critical` (only critical issues). To change this:

```bash
# Post critical + warning (skip suggestions)
python -m bot --pr 123 --repo venture --min-severity warning

# Post everything (critical + warning + suggestion)
python -m bot --pr 123 --repo venture --min-severity suggestion
```

## Running the Bot Manually

You can also run the bot from the command line to review any PR:

```bash
# Requires: ANTHROPIC_API_KEY env var and config.yaml

# Review a PR
python -m bot --pr 7342 --repo venture

# Dry run (print findings, don't post)
python -m bot --pr 7342 --repo venture --dry-run

# Only post critical issues
python -m bot --pr 7342 --repo venture --min-severity critical

# Keep previous bot reviews (don't dismiss)
python -m bot --pr 7342 --repo venture --no-dismiss
```

## Re-Mining Rules (Optional)

Rules are pre-mined and committed in `rules/sections/` (see `rules/sections/CHANGELOG.md` for when they were last updated). Re-mine when you want to incorporate newer PR review patterns.

### Prerequisites for mining

- [Claude CLI (`claude`)](https://docs.anthropic.com/en/docs/claude-cli) — used to extract and synthesize insights
- [GitHub CLI (`gh`)](https://cli.github.com/) — authenticated via `gh auth login`
- `config.yaml` — with your repos and scopes configured

### Running the pipeline

```bash
# Mine a single repo
python3 scripts/run_pipeline.py --repo venture --since 2025-01-01

# Mine all repos in config
python3 scripts/run_pipeline.py --all --since 2025-01-01

# Skip stages you've already run
python3 scripts/run_pipeline.py --repo venture --skip-refresh --skip-extract

# Resume a failed run
python3 scripts/run_pipeline.py --resume venture_all_2026-03-18
```

Options: `--max-parallel N` (default 10), `--batch-size N` (default 30)

### Pipeline stages

| Stage | What it does |
|-------|-------------|
| **Refresh** | Fetches PR review threads from GitHub via `gh api` |
| **Extract** | Sends threads to Claude to identify review insights |
| **Validate** | Validates extracted insights (auto-pass, ~99.9% rate) |
| **Topic Assignment** | Classifies insights into topics via keyword matching |
| **Synthesis** | Merges insights into best practices per topic via Claude |
| **Build** | Generates markdown rule files in `rules/sections/` |

After re-mining, commit the updated `rules/sections/` files and update `rules/sections/CHANGELOG.md`.

## Generating Review Prompts (Manual)

If you want to generate a review prompt without the bot posting anything:

```bash
# From a PR URL
python3 scripts/review.py https://github.com/angellist/nova/pull/7342

# From repo + PR number
python3 scripts/review.py angellist/nova 7342

# From local changes
python3 scripts/review.py --local
python3 scripts/review.py --local --base origin/develop

# Save to file (useful for piping to Claude)
python3 scripts/review.py -o review_prompt.md https://github.com/angellist/nova/pull/7342

# See which rules would be selected
python3 scripts/review.py --list-rules https://github.com/angellist/nova/pull/7342
```

## Limitations

- **Rules go stale.** The mined rules are a snapshot of how we reviewed PRs up to the date they were last mined (see `rules/sections/CHANGELOG.md`). If the team's patterns evolve and nobody re-mines, the rules drift. Plan to re-mine quarterly.
- **No substitute for human review.** The bot checks against known patterns — it can't catch novel bugs, bad product decisions, or architectural issues it hasn't seen before. "The bot didn't flag anything" does not mean the PR is good.
- **35 topics is a lot.** Not every rule will be relevant to every team. Skim through `rules/sections/` and remove topics that don't apply to your codebase to keep signal-to-noise high.

## Running Tests

```bash
pytest
```

## Project Structure

```
.claude/skills/pr-review/  # Claude Code skill for /pr-review
.github/workflows/         # Reusable GitHub Actions workflow

scripts/
  run_pipeline.py          # Mining pipeline orchestrator
  review.py                # Review prompt generator
  refresh.py               # Fetch PR threads from GitHub
  aggregate_extraction.py  # Merge extraction batch results
  aggregate_synthesis.py   # Merge synthesis results
  dispatch_synthesis.py    # Set up per-topic synthesis
  build_sections.py        # Generate markdown rule files
  utils.py                 # Shared utilities

bot/
  __main__.py              # Entry point for `python -m bot`
  review.py                # Review orchestrator
  claude_client.py         # Claude API integration
  github_client.py         # GitHub API operations
  diff_parser.py           # PR diff parsing and filtering
  scope_matcher.py         # Rule selection based on file scopes

rules/sections/            # Pre-mined review rules (35 topics, committed)
  CHANGELOG.md             # When rules were last mined
config.yaml.example        # Template configuration
references/                # Prompts and templates used by the mining pipeline
```
