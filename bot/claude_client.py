"""Build prompt, call Anthropic API, and parse structured review response."""

import json
import os
import re

import utils

SYSTEM_PROMPT = """\
You are a senior code reviewer for an engineering team. You review pull request \
diffs against the team's documented best practices.

Your job:
- Flag only CLEAR violations of the provided rules. Do not flag style nits, \
minor preferences, or things that are debatable.
- Each comment must cite which specific rule it relates to.
- Be concise and constructive. Suggest what to do, not just what's wrong.
- If the diff looks fine, return an empty array. Silence is better than noise.

Respond with ONLY a JSON array. No markdown fences, no explanation outside the array.
Each element must have exactly these fields:
{
  "file": "path/to/file.ext",
  "line": <integer line number from the diff where the issue is>,
  "severity": "critical" | "warning" | "suggestion",
  "rule_topic": "topic_name",
  "rule_title": "Title of the Specific Rule",
  "comment": "Clear, actionable explanation of the violation and how to fix it"
}

Prioritize by severity. Return at most %d comments, focusing on the most \
important issues first. Critical > Warning > Suggestion."""

USER_PROMPT_TEMPLATE = """\
## Team Best Practices

{rules}

---

## Pull Request Diff

{diff}"""

BRIEF_SYSTEM_PROMPT = """\
You are a senior engineer summarizing a pull request for a reviewer. Your goal \
is to reduce the reviewer's cognitive load so they can review this PR in under \
2 minutes.

Respond with ONLY a JSON object. No markdown fences, no explanation outside the object.
The object must have exactly these fields:
{
  "summary": "2-3 bullet points describing what changed (markdown list)",
  "why": "1-2 sentences explaining WHY this change was made",
  "risk_rationale": "1 sentence explaining the risk classification",
  "reviewer_focus": ["area 1 the reviewer should check", "area 2", ...],
  "rules_checked": ["rule_topic_1", "rule_topic_2", ...]
}

Be concise. Use plain language. Focus on what matters to the reviewer."""

BRIEF_USER_TEMPLATE = """\
## Risk Level: {risk}

## Matched Scopes: {scopes}

## PR Description
{pr_description}

## Rules Checked
{rules_checked}

## Diff

{diff}"""


def get_model() -> str:
    """Get the Claude model to use from config."""
    bot_config = utils.load_config().get("bot", {})
    return bot_config.get("model", "claude-sonnet-4-20250514")


def get_max_comments() -> int:
    """Get max comments per review from config."""
    bot_config = utils.load_config().get("bot", {})
    return bot_config.get("max_comments", 10)


def build_prompt(rules_text: str, diff_text: str) -> tuple[str, str]:
    """Build system and user prompts for Claude.

    Args:
        rules_text: Concatenated rule section content
        diff_text: Formatted diff text

    Returns:
        Tuple of (system_prompt, user_prompt)
    """
    max_comments = get_max_comments()
    system = SYSTEM_PROMPT % max_comments
    user = USER_PROMPT_TEMPLATE.format(rules=rules_text, diff=diff_text)
    return system, user


def call_claude(system_prompt: str, user_prompt: str) -> list[dict]:
    """Call the Anthropic API and parse the response.

    Args:
        system_prompt: System message for Claude
        user_prompt: User message with rules and diff

    Returns:
        List of review comment dicts

    Raises:
        RuntimeError: If API call fails or response can't be parsed
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install anthropic"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)
    model = get_model()

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    if not response.content:
        raise RuntimeError(f"Empty response from Claude (stop_reason={response.stop_reason})")

    text = response.content[0].text
    return parse_response(text)


def generate_brief(
    diff_text: str,
    pr_description: str,
    risk_level: str,
    matched_scopes: set[str],
    section_names: list[str],
) -> dict:
    """Generate a review brief summarizing the PR for the reviewer.

    Args:
        diff_text: Formatted diff text
        pr_description: PR description from GitHub (may be empty)
        risk_level: Risk classification ("High", "Medium", "Low")
        matched_scopes: Set of scope names matched from the diff
        section_names: List of rule section names that were checked

    Returns:
        Dict with keys: summary, why, risk_rationale, reviewer_focus, rules_checked

    Raises:
        RuntimeError: If API call fails
        ValueError: If response can't be parsed
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic package not installed. Run: pip install anthropic"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    user_prompt = BRIEF_USER_TEMPLATE.format(
        risk=risk_level,
        scopes=", ".join(sorted(matched_scopes)) if matched_scopes else "none",
        pr_description=pr_description or "(No PR description provided — summarize from diff only)",
        rules_checked=", ".join(section_names) if section_names else "none",
        diff=diff_text,
    )

    client = anthropic.Anthropic(api_key=api_key)
    model = get_model()

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=BRIEF_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    if not response.content:
        raise RuntimeError(f"Empty response from Claude (stop_reason={response.stop_reason})")

    text = response.content[0].text
    return parse_brief_response(text)


def parse_brief_response(text: str) -> dict:
    """Parse Claude's JSON response into a review brief dict.

    Args:
        text: Raw text response from Claude

    Returns:
        Dict with brief fields

    Raises:
        ValueError: If response cannot be parsed as valid JSON object
    """
    cleaned = text.strip()

    # Strip markdown code fences if present
    fence_match = re.match(r"```(?:json)?\s*\n(.*?)\n```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse brief response as JSON: {e}\nResponse: {text[:500]}")

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")

    required_fields = {"summary", "why", "risk_rationale", "reviewer_focus", "rules_checked"}
    missing = required_fields - set(data.keys())
    if missing:
        raise ValueError(f"Brief response missing fields: {missing}")

    return data


def parse_response(text: str) -> list[dict]:
    """Parse Claude's JSON response into review comments.

    Handles responses wrapped in markdown code fences.

    Args:
        text: Raw text response from Claude

    Returns:
        List of validated review comment dicts

    Raises:
        ValueError: If response cannot be parsed as valid JSON array
    """
    cleaned = text.strip()

    # Strip markdown code fences if present (may appear after preamble text)
    fence_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    else:
        # Try to find a raw JSON array in the text
        array_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if array_match:
            cleaned = array_match.group(0).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse Claude response as JSON: {e}\nResponse: {text[:500]}")

    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")

    required_fields = {"file", "line", "severity", "rule_topic", "rule_title", "comment"}
    valid_severities = {"critical", "warning", "suggestion"}
    validated = []

    for item in data:
        if not isinstance(item, dict):
            continue
        if not required_fields.issubset(item.keys()):
            continue
        if item["severity"] not in valid_severities:
            continue
        if not isinstance(item["line"], int) or item["line"] < 1:
            continue
        validated.append(item)

    # Sort by severity priority and cap at max_comments
    severity_order = {"critical": 0, "warning": 1, "suggestion": 2}
    validated.sort(key=lambda c: severity_order.get(c["severity"], 9))

    max_comments = get_max_comments()
    return validated[:max_comments]
