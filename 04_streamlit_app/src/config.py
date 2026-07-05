"""
Config Module — centralized project-wide constants and benchmark display
labels.

Single source of truth for branding strings, headline assumptions, and
disclosure-aware benchmark labels used across app.py and every Streamlit
page, so wording like the default risk-free rate or the "not official TRI"
caveat is defined once instead of being restated ad hoc per page.

Calculation-relevant constants that already exist in utils.py
(DATA_START_DATE, DEFAULT_RISK_FREE_RATE) are re-exported here rather than
redefined, so there remains exactly one place that can change their value
and no risk of the two modules drifting out of sync.
"""

from __future__ import annotations

import sys
from pathlib import Path

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from utils import DATA_START_DATE, DEFAULT_RISK_FREE_RATE  # noqa: E402,F401 - re-exported for centralized access

# ---------------------------------------------------------------------------
# Branding / headline constants
# ---------------------------------------------------------------------------

PROJECT_TITLE = "MF Risk Diagnostic Module"
PROJECT_TAGLINE = "What Risk Created the Return?"
BASE_PORTFOLIO_VALUE = 10_000_000
DISCLAIMER = "Educational analytics project. Not investment advice."

# ---------------------------------------------------------------------------
# Benchmark display labels — short, human-readable labels that always carry
# the proxy/synthetic caveat inline, so a chart legend, table cell, or
# caption never implies a benchmark is an official TRI series when it is
# not. These reflect the current source_quality of each benchmark per
# 02_processed_data/data_quality_report.csv (see the Methodology page and
# README §5/§7 for the underlying sourcing rules).
# ---------------------------------------------------------------------------

BENCHMARK_DISPLAY_LABELS = {
    "NIFTY50_TRI": "Nifty 50 proxy — not official TRI",
    "NIFTY100_TRI": "Nifty 100 proxy — not official TRI",
    "NIFTY500_TRI": "Nifty 500 proxy — not official TRI",
    "NIFTYSMALLCAP250_TRI": "Smallcap 250 synthetic/proxy approximation",
    "HYBRID_65_35": "Hybrid 65:35 synthetic benchmark",
}


def get_benchmark_display_label(benchmark_label: str) -> str:
    """
    Return the disclosure-aware display label for a benchmark_label code
    (e.g. 'NIFTY50_TRI' -> 'Nifty 50 proxy — not official TRI').

    Falls back to the raw code itself if it is not one of the five
    configured benchmarks, rather than raising — this is a display helper,
    not a validation gate.
    """
    return BENCHMARK_DISPLAY_LABELS.get(benchmark_label, str(benchmark_label))
