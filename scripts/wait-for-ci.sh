#!/usr/bin/env bash
# A release must use a commit whose main-branch CI has passed.
set -euo pipefail

attempts=${CI_WAIT_ATTEMPTS:-90}
interval=${CI_WAIT_INTERVAL:-10}

for ((attempt = 1; attempt <= attempts; attempt++)); do
    if ! result=$(gh run list --repo "$GITHUB_REPOSITORY" --workflow ci.yml \
        --branch main --event push --commit "$GITHUB_SHA" --limit 1 \
        --json status,conclusion \
        --jq '.[0] | [.status, (.conclusion // "")] | @tsv' 2>/dev/null); then
        result=""
    fi
    case "$result" in
        $'completed\tsuccess')
            echo "CI passed for $GITHUB_SHA"
            exit 0
            ;;
        $'completed\t'*)
            echo "::error::CI did not pass for $GITHUB_SHA: $result"
            exit 1
            ;;
    esac
    echo "Waiting for main-branch CI for $GITHUB_SHA ($attempt/$attempts)"
    if ((attempt < attempts)); then
        sleep "$interval"
    fi
done

echo "::error::Timed out waiting for main-branch CI for $GITHUB_SHA"
exit 1
