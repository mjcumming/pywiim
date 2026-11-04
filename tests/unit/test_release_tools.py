"""Exercise release safeguards without contacting GitHub or publishing."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.name == "nt", reason="Release scripts use a POSIX shell")


@pytest.fixture
def fake_tools(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """Put a controllable GitHub CLI at the front of PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$FAKE_GH_ARGS"\n'
        'printf "%s\\n" "${FAKE_GH_RESULT:-}"\nexit "${FAKE_GH_STATUS:-0}"\n'
    )
    gh.chmod(0o755)
    git = bin_dir / "git"
    git.write_text(
        '#!/bin/sh\ncase "$1" in\n'
        '  merge-base) exit "${FAKE_MAIN_STATUS:-0}" ;;\n'
        '  show-ref) exit "${FAKE_TAG_STATUS:-1}" ;;\n'
        '  rev-parse) printf "%s\\n" "${FAKE_TAG_COMMIT:-reviewed-commit}" ;;\n'
        "esac\n"
    )
    git.chmod(0o755)
    record = tmp_path / "gh-args"
    env = os.environ.copy()
    env.update(
        PATH=f"{bin_dir}{os.pathsep}{env['PATH']}",
        FAKE_GH_ARGS=str(record),
        GITHUB_REPOSITORY="mjcumming/pywiim",
        GITHUB_SHA="reviewed-commit",
        GITHUB_EVENT_NAME="workflow_dispatch",
        GITHUB_REF="refs/heads/main",
        TAG="v3.0.1",
        CI_WAIT_ATTEMPTS="1",
        CI_WAIT_INTERVAL="0",
    )
    return env, record


def workflow_step(name: str) -> str:
    """Read the actual publishing step so the tests exercise its shell code."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8"))
    return next(step["run"] for step in workflow["jobs"]["release"]["steps"] if step.get("name") == name)


@pytest.mark.parametrize(
    ("ref", "main_status", "tag_status", "tag_commit", "expected"),
    [
        ("refs/heads/main", "0", "1", "", 0),
        ("refs/heads/feature", "0", "1", "", 1),
        ("refs/heads/main", "1", "1", "", 1),
        ("refs/heads/main", "0", "0", "wrong-commit", 1),
        ("refs/heads/main", "0", "0", "reviewed-commit", 0),
    ],
)
def test_release_commit_and_existing_tag_are_verified(
    fake_tools: tuple[dict[str, str], Path],
    ref: str,
    main_status: str,
    tag_status: str,
    tag_commit: str,
    expected: int,
) -> None:
    env, _ = fake_tools
    env.update(
        GITHUB_REF=ref,
        FAKE_MAIN_STATUS=main_status,
        FAKE_TAG_STATUS=tag_status,
        FAKE_TAG_COMMIT=tag_commit,
    )
    run = subprocess.run(
        ["bash", "-e", "-c", workflow_step("Verify release commit is on main")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == expected


@pytest.mark.parametrize(
    ("project_version", "init_version", "expected"),
    [("3.0.1", "3.0.1", 0), ("3.0.1", "3.0.0", 1), ("3.0.2", "3.0.2", 1)],
)
def test_both_version_files_match_the_tag(
    fake_tools: tuple[dict[str, str], Path], tmp_path: Path, project_version: str, init_version: str, expected: int
) -> None:
    env, _ = fake_tools
    (tmp_path / "pyproject.toml").write_text(f'version = "{project_version}"\n')
    (tmp_path / "pywiim").mkdir()
    (tmp_path / "pywiim/__init__.py").write_text(f'__version__ = "{init_version}"\n')
    run = subprocess.run(
        ["bash", "-e", "-c", workflow_step("Check version files match the release tag")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == expected


@pytest.mark.parametrize(
    ("result", "gh_status", "expected"),
    [
        ("completed\tsuccess", "0", 0),
        ("completed\tfailure", "0", 1),
        ("in_progress\t", "0", 1),
        ("", "0", 1),
        ("completed\tsuccess", "1", 1),
    ],
)
def test_release_requires_successful_ci_for_the_main_commit(
    fake_tools: tuple[dict[str, str], Path], result: str, gh_status: str, expected: int
) -> None:
    env, record = fake_tools
    env.update(FAKE_GH_RESULT=result, FAKE_GH_STATUS=gh_status)
    run = subprocess.run(
        ["bash", str(ROOT / "scripts/wait-for-ci.sh")], env=env, capture_output=True, text=True, check=False
    )
    assert run.returncode == expected
    args = record.read_text().splitlines()
    assert args[args.index("--commit") + 1] == "reviewed-commit"
    assert args[args.index("--branch") + 1] == "main"
    assert args[args.index("--event") + 1] == "push"


def test_release_dispatches_prepared_main_version(fake_tools: tuple[dict[str, str], Path]) -> None:
    env, record = fake_tools
    run = subprocess.run(
        ["bash", str(ROOT / "scripts/release.sh"), "3.0.1"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0
    assert record.read_text().splitlines() == [
        "workflow",
        "run",
        "publish.yml",
        "--repo",
        "mjcumming/pywiim",
        "--ref",
        "main",
        "-f",
        "version=3.0.1",
    ]


def test_release_rejects_unprepared_version(fake_tools: tuple[dict[str, str], Path]) -> None:
    env, record = fake_tools
    run = subprocess.run(
        ["bash", str(ROOT / "scripts/release.sh"), "patch"], env=env, capture_output=True, text=True, check=False
    )
    assert run.returncode != 0
    assert not record.exists()


def test_manual_production_upload_is_disabled(fake_tools: tuple[dict[str, str], Path]) -> None:
    env, record = fake_tools
    run = subprocess.run(
        ["bash", str(ROOT / "scripts/publish.sh"), "prod"], env=env, capture_output=True, text=True, check=False
    )
    assert run.returncode != 0
    assert "make release" in run.stdout
    assert not record.exists()


@pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
def test_failed_parallel_tests_are_not_silently_retried(
    fake_tools: tuple[dict[str, str], Path], tmp_path: Path
) -> None:
    env, _ = fake_tools
    bin_dir = Path(env["PATH"].split(os.pathsep)[0])
    for name in ("black", "isort", "ruff", "mypy", "python"):
        tool = bin_dir / name
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(0o755)
    pytest_tool = bin_dir / "pytest"
    pytest_tool.write_text(
        '#!/bin/sh\necho called >> "$PYTEST_CALLS"\n' 'test "$(wc -l < "$PYTEST_CALLS")" -gt 1 && exit 0\nexit 1\n'
    )
    pytest_tool.chmod(0o755)
    calls = tmp_path / "pytest-calls"
    env["PYTEST_CALLS"] = str(calls)
    run = subprocess.run(["make", "check"], cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    assert run.returncode != 0
    assert calls.read_text().splitlines() == ["called"]
