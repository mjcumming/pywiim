# pywiim release process

Releases publish a reviewed commit from `main` to PyPI and GitHub. The
[Release and Publish workflow](../.github/workflows/publish.yml) is the
publishing path; local commands do not stage, commit, or push unrelated work.

## Prepare and review

1. Update `pyproject.toml` and `pywiim/__init__.py` to the same version.
2. Add a versioned entry to [CHANGELOG.md](../CHANGELOG.md). Describe
   user-visible fixes and compatibility changes.
3. Open a PR, review the changes, and pass CI. Merge it to `main`.
4. Verify the release workflow succeeds. It may reuse successful PR CI when
   that run recorded the exact release tree; otherwise it waits for CI on the
   merged commit. Device tests are useful when relevant and hardware is
   available; record what was tested.

Use semantic versioning and avoid a release containing no product changes.
Do not publish an unpublished dependency or commit the contents of another
checkout into this repository.

## Publish

From any checkout with an authenticated GitHub CLI:

```bash
make release VERSION=3.0.1
```

Replace the example with the version already merged to `main`. Alternatively,
run the **Release and Publish** GitHub Actions workflow on `main` and supply
that version. The workflow checks that the commit is on `main`, the version
files match, a changelog entry exists, and CI passed for the exact release
tree. It builds and publishes to PyPI, then creates the GitHub tag and
release with the same artifacts. A pushed version tag can also trigger the
same workflow and checks.

The command starts the workflow; it does not mean publication has succeeded.
Check the workflow result and the version on
[PyPI](https://pypi.org/project/pywiim/) and
[GitHub Releases](https://github.com/mjcumming/pywiim/releases). If WiiM needs
this version, verify it is available to package installers before pinning and
releasing the integration.

## Recovery

If the workflow fails, inspect the failing step before retrying. In particular,
PyPI may have accepted the package even if creating the GitHub release failed.
An already published version cannot be replaced: verify the published artifact
and commit before repairing the GitHub release or publishing a new version.
Never automatically stage all changes or force-update a published tag.
