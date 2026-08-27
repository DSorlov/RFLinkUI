#!/usr/bin/env python3
"""Create a throwaway virtualenv and run the test suite in it.

Usage::

    python3 scripts/test_runner.py            # run the tests
    python3 scripts/test_runner.py --clean    # rebuild the virtualenv first
    python3 scripts/test_runner.py -- -k sensor

Everything after ``--`` is forwarded to pytest.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv_ha_test"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def ensure_venv(*, clean: bool) -> None:
    """Create the virtualenv and install the test requirements."""
    if clean and VENV.exists():
        shutil.rmtree(VENV)
    if not PYTHON.exists():
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)

    subprocess.run(
        [str(PYTHON), "-m", "pip", "install", "--quiet", "--upgrade", "pip"],
        check=True,
    )
    subprocess.run(
        [
            str(PYTHON),
            "-m",
            "pip",
            "install",
            "--quiet",
            "--requirement",
            str(ROOT / "requirements_test.txt"),
        ],
        check=True,
    )


def run_tests(pytest_args: list[str]) -> int:
    """Run pytest inside the virtualenv."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT), env.get("PYTHONPATH", "")])
    result = subprocess.run(
        [str(PYTHON), "-m", "pytest", *pytest_args], cwd=ROOT, env=env, check=False
    )
    return result.returncode


def main() -> int:
    """Parse arguments and run the suite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clean", action="store_true", help="rebuild the virtualenv from scratch"
    )
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    pytest_args = args.pytest_args
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]

    ensure_venv(clean=args.clean)
    return run_tests(pytest_args)


if __name__ == "__main__":
    sys.exit(main())
