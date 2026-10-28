#!/usr/bin/env python3
"""Generate changelog entries using AI based on git commits since last release.

This script analyzes git commits since the last release tag and uses AI
to generate properly formatted changelog entries in Keep a Changelog format.
"""

import argparse
import subprocess
import sys

try:
    import openai
except ImportError:
    openai = None

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None


def get_last_release_tag() -> str | None:
    """Get the most recent release tag."""
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-version:refname"],
            capture_output=True,
            text=True,
            check=True,
        )
        tags = [tag.strip() for tag in result.stdout.strip().split("\n") if tag.strip()]
        # Filter to version tags (vX.Y.Z format)
        version_tags = [tag for tag in tags if tag.startswith("v") and tag[1:].replace(".", "").isdigit()]
        return version_tags[0] if version_tags else None
    except subprocess.CalledProcessError:
        return None


def get_commits_since_tag(tag: str) -> list[dict[str, str]]:
    """Get commits since the given tag."""
    try:
        result = subprocess.run(
            ["git", "log", f"{tag}..HEAD", "--pretty=format:%H|%s|%b", "--no-merges"],
            capture_output=True,
            text=True,
            check=True,
        )
        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 2)
            if len(parts) >= 2:
                commits.append(
                    {
                        "hash": parts[0],
                        "subject": parts[1],
                        "body": parts[2] if len(parts) > 2 else "",
                    }
                )
        return commits
    except subprocess.CalledProcessError:
        return []


def get_changed_files_since_tag(tag: str) -> list[str]:
    """Get list of changed files since the given tag."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{tag}..HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except subprocess.CalledProcessError:
        return []


def generate_changelog_with_openai(commits: list[dict[str, str]], changed_files: list[str]) -> str:
    """Generate changelog using OpenAI API."""
    import os

    if not openai:
        raise ImportError("openai package not installed. Install with: pip install openai")

    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY environment variable not set. " "Set it with: export OPENAI_API_KEY='your-key-here'"
        )

    client = openai.OpenAI(api_key=api_key)

    # Build commit summary
    commit_text = "\n".join(
        [
            f"- {c['subject']}" + (f"\n  {c['body']}" if c["body"].strip() else "")
            for c in commits[:50]  # Limit to 50 commits
        ]
    )

    changed_files_text = "\n".join(sorted(set(changed_files))[:30])  # Limit to 30 files

    prompt = f"""Analyze the following git commits and changed files since the last release, and generate changelog entries in Keep a Changelog format.

Commits:
{commit_text}

Changed files:
{changed_files_text}

Generate changelog entries organized by category:
- ### Added (new features)
- ### Changed (changes in existing functionality)
- ### Deprecated (soon-to-be removed features)
- ### Removed (removed features)
- ### Fixed (bug fixes)
- ### Security (vulnerability fixes)

Format each entry as a bullet point with a clear, concise description. Group related changes together.
Focus on user-facing changes and important technical improvements.
Skip routine maintenance, formatting, or test-only changes unless they're significant.

Output ONLY the changelog entries (no markdown headers, no explanations). Start directly with ### Added, ### Changed, etc.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use cheaper model for changelog generation
            messages=[
                {
                    "role": "system",
                    "content": "You are a technical writer specializing in changelog generation. You create clear, concise, and well-organized changelog entries.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,  # Lower temperature for more consistent output
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise RuntimeError(f"Failed to generate changelog with OpenAI: {e}")


def generate_changelog_with_anthropic(commits: list[dict[str, str]], changed_files: list[str]) -> str:
    """Generate changelog using Anthropic Claude API."""
    import os

    if not Anthropic:
        raise ImportError("anthropic package not installed. Install with: pip install anthropic")

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable not set. " "Set it with: export ANTHROPIC_API_KEY='your-key-here'"
        )

    client = Anthropic(api_key=api_key)

    # Build commit summary
    commit_text = "\n".join(
        [
            f"- {c['subject']}" + (f"\n  {c['body']}" if c["body"].strip() else "")
            for c in commits[:50]  # Limit to 50 commits
        ]
    )

    changed_files_text = "\n".join(sorted(set(changed_files))[:30])  # Limit to 30 files

    prompt = f"""Analyze the following git commits and changed files since the last release, and generate changelog entries in Keep a Changelog format.

Commits:
{commit_text}

Changed files:
{changed_files_text}

Generate changelog entries organized by category:
- ### Added (new features)
- ### Changed (changes in existing functionality)
- ### Deprecated (soon-to-be removed features)
- ### Removed (removed features)
- ### Fixed (bug fixes)
- ### Security (vulnerability fixes)

Format each entry as a bullet point with a clear, concise description. Group related changes together.
Focus on user-facing changes and important technical improvements.
Skip routine maintenance, formatting, or test-only changes unless they're significant.

Output ONLY the changelog entries (no markdown headers, no explanations). Start directly with ### Added, ### Changed, etc.
"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Use cheaper model
            max_tokens=2000,
            extra_body={"temperature": 0.3},
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        raise RuntimeError(f"Failed to generate changelog with Anthropic: {e}")


def main():
    import os

    parser = argparse.ArgumentParser(description="Generate changelog entries using AI")
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic", "auto"],
        default="auto",
        help="AI provider to use (default: auto-detect based on available API keys)",
    )
    parser.add_argument(
        "--tag",
        help="Git tag to compare against (default: latest release tag)",
    )
    parser.add_argument(
        "--output",
        help="Output file (default: stdout)",
    )

    args = parser.parse_args()

    # Determine tag
    tag = args.tag or get_last_release_tag()
    if not tag:
        print("Error: No release tag found and --tag not specified", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing commits since {tag}...", file=sys.stderr)

    # Get commits and changed files
    commits = get_commits_since_tag(tag)
    changed_files = get_changed_files_since_tag(tag)

    if not commits:
        print("No commits found since last release.", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(commits)} commits and {len(changed_files)} changed files", file=sys.stderr)

    # Determine provider
    provider = args.provider
    if provider == "auto":
        openai_key = os.getenv("OPENAI_API_KEY")
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")

        if openai_key and openai:
            provider = "openai"
        elif anthropic_key and Anthropic:
            provider = "anthropic"
        else:
            print("Error: No AI provider available. Set OPENAI_API_KEY or ANTHROPIC_API_KEY", file=sys.stderr)
            sys.exit(1)

    # Generate changelog
    print(f"Generating changelog with {provider}...", file=sys.stderr)
    try:
        if provider == "openai":
            changelog = generate_changelog_with_openai(commits, changed_files)
        elif provider == "anthropic":
            changelog = generate_changelog_with_anthropic(commits, changed_files)
        else:
            print(f"Error: Unknown provider: {provider}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error generating changelog: {e}", file=sys.stderr)
        sys.exit(1)

    # Output
    if args.output:
        with open(args.output, "w") as f:
            f.write(changelog)
        print(f"Changelog written to {args.output}", file=sys.stderr)
    else:
        print(changelog)


if __name__ == "__main__":
    main()
