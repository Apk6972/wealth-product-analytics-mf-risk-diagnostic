"""
Tests: all Python files compile and core src modules are importable.

Requirement 6 — syntax check via py_compile (no code execution, safe for
Streamlit pages that run st.xxx calls at module level).

Requirement 7 — import smoke tests for the computation/utility modules in
04_streamlit_app/src/.  Pages are intentionally excluded from direct import
because they execute Streamlit rendering calls at the top level; py_compile
above already catches any syntax errors in those files.

disclosures.py is tested via py_compile only; it imports `streamlit as st`
at the top level, and importing it during testing would require a live
Streamlit server context that is unavailable in a standard pytest run.
"""

from __future__ import annotations

import importlib
import py_compile
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "04_streamlit_app" / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------------------------
# Helper: collect all project Python files, deduplicated and sorted
# ---------------------------------------------------------------------------


def _collect_python_files() -> list[Path]:
    excluded_dirs = {"venv", ".venv", "__pycache__", ".git", "node_modules"}
    seen: set[Path] = set()
    results: list[Path] = []
    for p in sorted(PROJECT_ROOT.rglob("*.py")):
        resolved = p.resolve()
        if resolved in seen:
            continue
        if any(part in excluded_dirs for part in resolved.parts):
            continue
        seen.add(resolved)
        results.append(resolved)
    return results


_ALL_PY_FILES = _collect_python_files()
_ALL_PY_IDS = [str(p.relative_to(PROJECT_ROOT).as_posix()) for p in _ALL_PY_FILES]


# ---------------------------------------------------------------------------
# Requirement 6 — every Python file must compile without a syntax error
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("py_file", _ALL_PY_FILES, ids=_ALL_PY_IDS)
def test_python_file_compiles(py_file: Path) -> None:
    """py_compile checks byte-compilation without executing module-level code."""
    try:
        py_compile.compile(str(py_file), doraise=True)
    except py_compile.PyCompileError as exc:
        pytest.fail(
            f"Syntax error in {py_file.relative_to(PROJECT_ROOT).as_posix()}: {exc}"
        )


# ---------------------------------------------------------------------------
# Requirement 7 — core src modules must import without crashing
#
# Modules in this list have no module-level Streamlit dependency and contain
# only pure-Python / pandas / numpy / plotly / scipy imports.  If a
# third-party package listed in requirements.txt is absent the test will fail
# with a clear ImportError — the fix is `pip install -r requirements.txt`.
# ---------------------------------------------------------------------------

# disclosures.py is intentionally absent from direct import tests.
# It imports `streamlit as st` at the top level; while streamlit itself is
# importable without a running server, keeping disclosures.py out of this list
# prevents unexpected side-effects in minimal CI environments where the full
# Streamlit stack may not be initialised.  It is covered by py_compile above.
_IMPORTABLE_SRC_MODULES = [
    "utils",
    "config",
    "formatting",
    "data_loader",
    "returns",
    "metrics",
    "data_cleaning",
    "benchmarks",
    "rolling_metrics",
    "stress",
    "attribution",
    "suitability",
    "charts",
    "api_fetch",
]


@pytest.mark.parametrize("module_name", _IMPORTABLE_SRC_MODULES)
def test_src_module_imports_cleanly(module_name: str) -> None:
    """
    Each src module must be importable without raising any exception.

    Failures here indicate either:
    - a missing local module (broken internal import chain), or
    - a missing third-party dependency (run pip install -r requirements.txt).
    """
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        pytest.fail(
            f"ImportError while importing src module '{module_name}': {exc}\n"
            "If this is a third-party package, run: pip install -r requirements.txt\n"
            "If this is a local module, check the import chain in src/."
        )
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"Unexpected {type(exc).__name__} while importing src module "
            f"'{module_name}': {exc}"
        )
