# Contributing to pywiim

pywiim owns device communication, parsing, capabilities, and player/group
behavior. Home Assistant entities and services belong in the
[WiiM integration](https://github.com/mjcumming/wiim). Keep the repositories,
commits, and releases separate.

## Development

Python 3.11 or newer is required. Create or activate a virtual environment and
install the development dependencies:

```bash
pip install -e ".[dev]"
```

Make a focused branch and describe the problem and solution in the pull
request; link an existing issue when useful. Preserve unrelated local changes
and stage only the files intended for the change. Use a separate worktree if
the checkout contains other work.

Use type hints and the existing asynchronous I/O and error-handling patterns.
Handle unsupported commands, malformed responses, timeouts, and device
differences where they affect the change. Do not assume a successful HTTP
response means that a device applied a setting.

## Tests and review

- Add focused tests for changed behavior, including meaningful failure paths
  and regression tests for bugs. Use existing fixtures and mocks for device
  communication.
- Run the relevant tests while developing. After pushing a release candidate
  PR and before merging it, run `python scripts/prepare_release.py` with Docker
  running. It checks the clean, committed tree on Python 3.11 and 3.12 and
  reuses a previous local success for the same tree. Use `--force` to rerun.
  GitHub CI and Codecov still run independently; see the
  [release process](docs/RELEASE_PROCESS.md). `make check` remains useful
  during development.
- Test on hardware when the behavior depends on device or firmware responses
  and a suitable device is available. Record the model and firmware, preserve
  device settings, and state clearly when hardware validation was not possible.
- Review each change in proportion to its risk and address actionable review
  feedback before merging. A maintainer may review routine work themselves;
  request another reviewer for changes that would benefit from independent
  review or when one is requested. Do not represent a self-review as an
  independent review.

Update user or API documentation when behavior changes, and add a changelog
entry when relevant to users. Record durable, non-obvious trade-offs in
[ADRs](docs/design/adr/README.md); ordinary fixes do not need a new ADR.

## Releasing

Prepare version files and changelog in a reviewed PR. After the PR is merged
and CI passes, publish from main using the
[release process](docs/RELEASE_PROCESS.md). Publish and verify pywiim before a
WiiM release that depends on the new library version.

For bug reports, include reproduction steps, expected and actual behavior,
device model and firmware when relevant, and logs with sensitive information
removed.

More detail: [development guide](docs/development/DEVELOPMENT.md) and
[API reference](docs/integration/API_REFERENCE.md).
