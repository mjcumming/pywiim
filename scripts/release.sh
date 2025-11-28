#!/bin/bash
# Automated release script: lint, format, bump version, commit, push, and create GitHub release
# Usage: ./scripts/release.sh [patch|minor|major]
# Requires: GitHub CLI (gh) for creating releases (optional, will warn if missing)

set -e  # Exit on error

# Load environment variables from .bashrc if GH_TOKEN is not already set
if [ -z "$GH_TOKEN" ] && [ -f ~/.bashrc ]; then
    # Source .bashrc to get GH_TOKEN if it's defined there
    # Use eval to properly export the variable from .bashrc
    eval "$(grep "^export GH_TOKEN=" ~/.bashrc 2>/dev/null || true)"
fi

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Use python3 from PATH (or venv if activated)
PYTHON=${PYTHON:-python3}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Function to extract changelog entry for a version
extract_changelog() {
    local version=$1
    local changelog_file="CHANGELOG.md"
    
    if [ ! -f "$changelog_file" ]; then
        warn "CHANGELOG.md not found, skipping changelog extraction"
        return 1
    fi
    
    # First, try to find the section for this specific version (e.g., "## [1.0.25]")
    local start_line=$(grep -n "^## \[$version\]" "$changelog_file" | cut -d: -f1)
    
    if [ -z "$start_line" ]; then
        # Version entry not found, try to use "Unreleased" section as fallback
        start_line=$(grep -n "^## \[Unreleased\]" "$changelog_file" | cut -d: -f1)
        
        if [ -z "$start_line" ]; then
            warn "Changelog entry for version $version not found, and no [Unreleased] section found"
            return 1
        else
            info "Using [Unreleased] section from CHANGELOG.md (version entry not found yet)"
        fi
    fi
    
    # Find the next version section or end of file
    local end_line=$(awk -v start="$start_line" 'NR > start && /^## \[/ {print NR-1; exit}' "$changelog_file")
    
    if [ -z "$end_line" ]; then
        # No next version found, read to end of file (but skip the link references at the bottom)
        end_line=$(grep -n "^\[Unreleased\]:" "$changelog_file" | cut -d: -f1)
        if [ -z "$end_line" ]; then
            end_line=$(wc -l < "$changelog_file")
        else
            end_line=$((end_line - 1))
        fi
    fi
    
    # Extract the changelog section (skip the version header line, keep content)
    sed -n "$((start_line + 1)),${end_line}p" "$changelog_file"
}

# Get version bump type (default: patch)
BUMP_TYPE=${1:-patch}
if [[ ! "$BUMP_TYPE" =~ ^(patch|minor|major)$ ]]; then
    error "Invalid bump type: $BUMP_TYPE"
    echo "Usage: $0 [patch|minor|major]"
    exit 1
fi

# Get current version from pyproject.toml
CURRENT_VERSION=$(grep -E '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
info "Current version: $CURRENT_VERSION"

# Calculate new version
IFS='.' read -ra VERSION_PARTS <<< "$CURRENT_VERSION"
MAJOR=${VERSION_PARTS[0]}
MINOR=${VERSION_PARTS[1]}
PATCH=${VERSION_PARTS[2]}

case $BUMP_TYPE in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
esac

NEW_VERSION="$MAJOR.$MINOR.$PATCH"
info "New version: $NEW_VERSION"

# Step 1: Format code
step "Formatting code with black..."
$PYTHON -m black pywiim tests

step "Sorting imports with isort..."
$PYTHON -m isort pywiim tests

# Step 2: Lint (must pass - no auto-fix for critical errors)
step "Linting with ruff (strict mode - no auto-fix)..."
if ! $PYTHON -m ruff check pywiim tests; then
    error "Ruff linting failed! Fix errors before releasing."
    error "Run 'ruff check pywiim tests' to see errors, or 'ruff check --fix pywiim tests' to auto-fix."
    exit 1
fi

step "Running all CI checks (format, lint, typecheck, tests)..."
if [ ! -f "./check.sh" ]; then
    error "check.sh not found! Cannot run CI checks."
    exit 1
fi
if ! ./check.sh; then
    error "Type checking failed! Fix errors before releasing."
    exit 1
fi

# Step 3: Run tests (must pass)
step "Running tests with pytest..."
if ! $PYTHON -m pytest tests/ --ignore=tests/integration/test_real_device.py -v; then
    error "Tests failed! Fix failing tests before releasing."
    exit 1
fi

info "All validation checks passed ✓"

# Step 4: Update CHANGELOG.md
step "Updating CHANGELOG.md..."
CHANGELOG_FILE="CHANGELOG.md"
TODAY=$(date +%Y-%m-%d)

# Check if [Unreleased] section exists and has content
if grep -q "^## \[Unreleased\]" "$CHANGELOG_FILE"; then
    # Check if [Unreleased] section has actual content (not just empty)
    UNRELEASED_START=$(grep -n "^## \[Unreleased\]" "$CHANGELOG_FILE" | cut -d: -f1)
    NEXT_SECTION=$(awk -v start="$UNRELEASED_START" 'NR > start && /^## \[/ {print NR; exit}' "$CHANGELOG_FILE")
    
    if [ -z "$NEXT_SECTION" ]; then
        # No next section, check if there's content after [Unreleased]
        UNRELEASED_LINES=$(tail -n +$((UNRELEASED_START + 1)) "$CHANGELOG_FILE" | grep -v '^$' | wc -l)
    else
        # Check content between [Unreleased] and next section
        UNRELEASED_LINES=$(sed -n "$((UNRELEASED_START + 1)),$((NEXT_SECTION - 1))p" "$CHANGELOG_FILE" | grep -v '^$' | wc -l)
    fi
    
    if [ "$UNRELEASED_LINES" -eq 0 ]; then
        error "CHANGELOG.md [Unreleased] section exists but is empty!"
        error "You must add changelog entries under [Unreleased] before releasing."
        error "Aborting release."
        exit 1
    fi
    
    # Create temporary file with updated changelog
    awk -v version="$NEW_VERSION" -v date="$TODAY" '
        /^## \[Unreleased\]/ {
            print "## [Unreleased]"
            print ""
            print "## [" version "] - " date
            next
        }
        { print }
    ' "$CHANGELOG_FILE" > "${CHANGELOG_FILE}.tmp"
    
    mv "${CHANGELOG_FILE}.tmp" "$CHANGELOG_FILE"
    info "Moved [Unreleased] content to [$NEW_VERSION] - $TODAY"
else
    error "No [Unreleased] section found in CHANGELOG.md!"
    error "You must add changelog entries under [Unreleased] before releasing."
    error "Aborting release."
    exit 1
fi

# Step 5: Update version in pyproject.toml
step "Updating version in pyproject.toml..."
sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml

# Step 6: Update version in __init__.py
step "Updating version in pywiim/__init__.py..."
sed -i "s/^__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" pywiim/__init__.py

# Step 7: Verify versions are updated
PYPROJECT_VERSION=$(grep -E '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
INIT_VERSION=$(grep -E '^__version__ = ' pywiim/__init__.py | sed 's/__version__ = "\(.*\)"/\1/')

if [ "$PYPROJECT_VERSION" != "$NEW_VERSION" ] || [ "$INIT_VERSION" != "$NEW_VERSION" ]; then
    error "Version update failed!"
    echo "  pyproject.toml: $PYPROJECT_VERSION (expected $NEW_VERSION)"
    echo "  __init__.py: $INIT_VERSION (expected $NEW_VERSION)"
    exit 1
fi

info "Version updated successfully in both files"

# Step 8: Final validation before commit
step "Running final validation checks before commit..."
# Re-run critical checks one more time to ensure nothing broke
if ! $PYTHON -m ruff check pywiim tests > /dev/null 2>&1; then
    error "Final ruff check failed! Aborting release."
    error "Run 'ruff check pywiim tests' to see errors."
    exit 1
fi

if ! ./check.sh > /dev/null 2>&1; then
    error "Final CI checks failed! Aborting release."
    exit 1
fi

info "Final validation checks passed ✓"

# Step 9: Check git status
step "Checking git status..."
if [ -z "$(git status --porcelain)" ]; then
    warn "No changes to commit. All files are up to date."
    exit 0
fi

# Step 10: Stage changes
step "Staging changes..."
git add -A

# Step 11: Commit
step "Committing changes..."
git commit -m "Release v$NEW_VERSION

- Moved [Unreleased] to [$NEW_VERSION] in CHANGELOG.md
- Bumped version to $NEW_VERSION
- All linting and tests passed"

# Step 12: Create version tag
step "Creating version tag v$NEW_VERSION..."
git tag -a "v$NEW_VERSION" -m "Release version $NEW_VERSION"

# Step 13: Push commits and tags
step "Pushing commits and tags to remote..."
# Get the current branch name
CURRENT_BRANCH=$(git branch --show-current)
# Push commits and tags together to ensure GitHub Actions workflow triggers
# Using explicit remote and branch to ensure tags are pushed correctly
git push origin "$CURRENT_BRANCH" --tags

# Verify tag was pushed
if git ls-remote --tags origin | grep -q "refs/tags/v$NEW_VERSION"; then
    info "Tag v$NEW_VERSION successfully pushed to remote"
    info "GitHub Actions workflow should trigger automatically to publish to PyPI"
else
    warn "Tag v$NEW_VERSION may not have been pushed correctly"
    warn "Please verify manually: git ls-remote --tags origin | grep v$NEW_VERSION"
fi

# Step 14: Create GitHub release (if GitHub CLI is available and authenticated)
if command -v gh &> /dev/null; then
    # Check if authenticated (either via stored auth or GH_TOKEN env var)
    IS_AUTHENTICATED=false
    if gh auth status &> /dev/null; then
        IS_AUTHENTICATED=true
    elif [ -n "$GH_TOKEN" ]; then
        # GH_TOKEN is set, use it for authentication
        IS_AUTHENTICATED=true
        info "Using GH_TOKEN environment variable for authentication..."
    fi
    
    if [ "$IS_AUTHENTICATED" = true ]; then
        step "Creating GitHub release v$NEW_VERSION..."
        
        # Extract changelog for this version
        CHANGELOG_NOTES=$(extract_changelog "$NEW_VERSION")
        
        if [ -n "$CHANGELOG_NOTES" ]; then
            # Create release with changelog notes
            if echo "$CHANGELOG_NOTES" | gh release create "v$NEW_VERSION" \
                --title "Release v$NEW_VERSION" \
                --notes-file - \
                --target main 2>&1; then
                info "GitHub release created successfully!"
            else
                warn "Failed to create GitHub release (but version was tagged and pushed)"
                warn "You can create it manually at: https://github.com/mjcumming/pywiim/releases/new"
            fi
        else
            # Create release without notes (fallback)
            warn "Could not extract changelog, creating release without notes"
            if gh release create "v$NEW_VERSION" \
                --title "Release v$NEW_VERSION" \
                --notes "Release version $NEW_VERSION" \
                --target main 2>&1; then
                info "GitHub release created successfully!"
            else
                warn "Failed to create GitHub release (but version was tagged and pushed)"
                warn "You can create it manually at: https://github.com/mjcumming/pywiim/releases/new"
            fi
        fi
    else
        warn "GitHub CLI found but not authenticated. Skipping GitHub release creation."
        warn "To authenticate, run: gh auth login"
        warn "Or create release manually at: https://github.com/mjcumming/pywiim/releases/new"
    fi
else
    warn "GitHub CLI (gh) not found. Skipping GitHub release creation."
    warn "To create a release manually:"
    warn "  1. Install GitHub CLI: https://cli.github.com/"
    warn "  2. Run: gh auth login"
    warn "  3. Or create it manually at: https://github.com/mjcumming/pywiim/releases/new"
fi

info "Release complete! Version bumped to $NEW_VERSION, tagged, and pushed to remote."

