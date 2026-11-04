ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /deps
COPY pyproject.toml ./
# Install the same project and dev dependencies as CI without copying source
# into this layer, so changes to application code do not reinstall them.
RUN python -c 'import subprocess, sys, tomllib; p = tomllib.load(open("pyproject.toml", "rb"))["project"]; subprocess.check_call([sys.executable, "-m", "pip", "install", "setuptools>=68", "wheel", *p["dependencies"], *p["optional-dependencies"]["dev"]])'

WORKDIR /workspace
