"""
Formatting Module — shared display-formatting helpers under one import
path.

The actual formatting logic (Indian-digit-grouped INR, compact Lakh/Crore
currency, percent formatting) already lives in utils.py and is used
throughout metrics.py, charts.py, and the existing Streamlit pages; this
module does not duplicate that logic. It re-exports those helpers under
formatting.py — alongside the new benchmark-label formatter — so the
config / formatting / disclosures module trio added in Phase 2 has one
clear, discoverable place to import display helpers from, without
changing any existing utils.py call site.
"""

from __future__ import annotations

import sys
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from utils import (  # noqa: E402,F401 - re-exported
    format_inr,
    format_inr_compact,
    format_percent,
)

from config import get_benchmark_display_label  # noqa: E402


def format_benchmark_label(benchmark_label: str) -> str:
    """
    Disclosure-aware display label for a benchmark_label code, e.g.
    'HYBRID_65_35' -> 'Hybrid 65:35 synthetic benchmark'.

    Thin alias over config.get_benchmark_display_label() — grouped here
    because, from a caller's perspective, choosing how to display a
    benchmark code is a formatting concern.
    """
    return get_benchmark_display_label(benchmark_label)
