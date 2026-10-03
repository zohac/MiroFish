"""Guard against syntax breakage in the simulation entry-point scripts.

These scripts are launched as subprocesses by the API layer, so a syntax error
never surfaces in the unit test suite -- it only appears as a failed simulation
process with an opaque exit code. Compiling them here turns that into a normal
test failure.
"""

import py_compile
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def script_paths():
    return sorted(SCRIPTS_DIR.glob("*.py"))


def test_scripts_directory_is_discovered():
    assert script_paths(), f"no simulation scripts found in {SCRIPTS_DIR}"


@pytest.mark.parametrize("path", script_paths(), ids=lambda p: p.name)
def test_script_compiles(path: Path):
    py_compile.compile(str(path), doraise=True)


@pytest.mark.parametrize(
    "name",
    [
        "run_parallel_simulation.py",
        "run_twitter_simulation.py",
        "run_reddit_simulation.py",
    ],
)
def test_opencode_compat_helper_is_importable(name: str):
    """The OpenCode-aware headers/effort helpers must be wired into each runner."""
    source = (SCRIPTS_DIR / name).read_text(encoding="utf-8")

    assert "from app.utils.llm_compat import" in source
    assert "llm_request_headers" in source
    assert "llm_completion_kwargs" in source