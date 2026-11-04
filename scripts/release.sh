#!/usr/bin/env bash
# Publish a prepared and merged main-branch version through GitHub Actions.
set -euo pipefail

version=${1:-}
if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ $# != 1 ]]; then
    echo "Usage: $0 X.Y.Z"
    echo "First merge the matching version files and changelog to main."
    exit 1
fi

gh workflow run publish.yml --repo mjcumming/pywiim --ref main -f "version=$version"
echo "Release requested for $version. Check the Release and Publish workflow and PyPI."
