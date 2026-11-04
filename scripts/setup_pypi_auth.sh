#!/usr/bin/env bash
# Production publishing uses GitHub Actions trusted publishing.
echo "Production releases use GitHub Actions; no local PyPI token is needed."
echo "For optional TestPyPI uploads, configure Twine using its keyring or environment variables."
