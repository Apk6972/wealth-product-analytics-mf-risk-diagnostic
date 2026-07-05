"""
Shared pytest configuration for the MF Risk Diagnostic Module test suite.

Adds 04_streamlit_app/src to sys.path so that the src/ computation modules
(utils, metrics, data_loader, etc.) can be imported by name in tests without
requiring a package-install step.  This mirrors the path-setup pattern each
src module already applies to itself at import time.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "04_streamlit_app" / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
