#!/usr/bin/env bash
# Optional isolated TestPyPI upload. Production uses GitHub Actions.
set -euo pipefail

if [[ ${1:-} == prod ]]; then
    echo "Production releases use GitHub Actions: make release VERSION=X.Y.Z"
    exit 1
fi
if [[ $# != 1 || $1 != test ]]; then
    echo "Usage: $0 test"
    exit 1
fi

python - <<'PY'
import subprocess
import sys
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory(prefix="pywiim-testpypi-") as directory:
    subprocess.run([sys.executable, "-m", "build", "--outdir", directory], check=True)
    artifacts = sorted(str(path) for path in Path(directory).iterdir() if path.suffix in {".whl", ".gz"})
    if not artifacts:
        raise SystemExit("Build produced no distribution artifacts")
    subprocess.run([sys.executable, "-m", "twine", "upload", "--repository", "testpypi", *artifacts], check=True)
PY
