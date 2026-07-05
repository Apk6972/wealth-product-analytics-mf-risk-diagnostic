"""
Disclosures Module — source-quality-aware banners shown on every Streamlit
page.

Centralizes the "how fresh and trustworthy is the data behind this page"
messaging so every page displays it identically, per
00_project_control/model_governance.md's disclosure obligations. Reads
only from 02_processed_data/data_quality_report.csv (via data_loader.py) —
never fetches live data, never modifies any processed CSV, and never lets
a raw exception or stack trace reach the page: any read failure degrades
to an st.warning() explaining what is missing instead of raising.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd
import streamlit as st

_THIS_FILE = Path(__file__).resolve()
_SRC_DIR = _THIS_FILE.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import data_loader as dl  # noqa: E402
from utils import is_dataframe_usable  # noqa: E402

REFRESH_COMMAND = "python 04_streamlit_app/refresh_data.py"

# source_quality values that mean "not an official, directly-observed
# market series" — surfaced here so the banner's proxy warning and the
# per-page benchmark caveats (Benchmark Behaviour, Methodology) agree on
# exactly which codes count as a proxy/approximation.
PROXY_SOURCE_QUALITIES = ("PRICE_INDEX_PROXY_NOT_TRI", "DISCLOSED_APPROXIMATION")

BENCHMARK_RELATIVE_CAVEAT = (
    "Benchmark-relative analytics on this page are **educational diagnostics**, not official "
    "performance attribution. Some benchmark series are price-index proxies or disclosed "
    "approximations, not official Total Return Index (TRI) data — check `source_quality` before "
    "drawing conclusions."
)


def _safe_load_data_quality_report() -> Optional[pd.DataFrame]:
    """Load the data quality report without ever raising past this function.
    Any read failure (missing file, corrupt CSV, unexpected schema) is
    treated the same as "not available yet" by the caller."""
    try:
        return dl.load_data_quality_report()
    except Exception:  # noqa: BLE001 - this banner must never crash a page
        return None


def render_data_quality_banner(stop_on_fail: bool = True) -> None:
    """
    Render a compact data-quality banner, intended to be called near the
    top of every Streamlit page (right after the page title/caption, before
    any processed data is used for charts or metrics).

    Shows, in one bordered container:
    - the latest available data date across all rows (max of `last_date`),
    - the count of PASS / WARNING / FAIL rows in the report, and
    - a clear warning naming any benchmark rows sourced as a price-index
      proxy or disclosed approximation, plus a standing reminder that
      benchmark-relative analytics are educational diagnostics, not
      official attribution.

    If any row has status == 'FAIL', also renders an st.error() (not a raw
    exception) naming the affected series and, when `stop_on_fail` is True
    (the default), calls st.stop() so only the current page halts —
    navigation to other pages is unaffected.
    """
    report = _safe_load_data_quality_report()

    if not is_dataframe_usable(report):
        st.warning(
            "`02_processed_data/data_quality_report.csv` is missing or empty, so data-quality status "
            "cannot be shown for this page. Run the refresh pipeline to generate it:"
        )
        st.code(REFRESH_COMMAND, language="bash")
        return

    status_column = report["status"] if "status" in report.columns else pd.Series(dtype=str)
    status_counts = status_column.value_counts()
    pass_count = int(status_counts.get("PASS", 0))
    warning_count = int(status_counts.get("WARNING", 0))
    fail_count = int(status_counts.get("FAIL", 0))

    latest_date_display = "N/A"
    if "last_date" in report.columns:
        parsed_dates = pd.to_datetime(report["last_date"], errors="coerce")
        if parsed_dates.notna().any():
            latest_date_display = parsed_dates.max().date().isoformat()

    proxy_labels: List[str] = []
    if {"asset_type", "source_quality", "fund_label_or_benchmark_label"}.issubset(report.columns):
        benchmark_rows = report[report["asset_type"] == "BENCHMARK"]
        proxy_rows = benchmark_rows[benchmark_rows["source_quality"].isin(PROXY_SOURCE_QUALITIES)]
        proxy_labels = sorted(proxy_rows["fund_label_or_benchmark_label"].dropna().astype(str).unique().tolist())

    with st.container(border=True):
        header_columns = st.columns(4)
        header_columns[0].metric("Latest Data Date", latest_date_display)
        header_columns[1].metric("PASS", pass_count)
        header_columns[2].metric("WARNING", warning_count)
        header_columns[3].metric("FAIL", fail_count)

        if proxy_labels:
            st.warning(
                "Proxy / disclosed-approximation benchmark series in this run: "
                + ", ".join(proxy_labels)
                + ". "
                + BENCHMARK_RELATIVE_CAVEAT
            )
        else:
            st.caption(BENCHMARK_RELATIVE_CAVEAT)

    if fail_count > 0:
        failed_labels: List[str] = []
        if "fund_label_or_benchmark_label" in report.columns:
            failed_labels = (
                report.loc[status_column == "FAIL", "fund_label_or_benchmark_label"]
                .dropna()
                .astype(str)
                .tolist()
            )
        failure_detail = f" ({', '.join(failed_labels)})" if failed_labels else ""
        st.error(
            f"Data quality check FAILED for {fail_count} series{failure_detail}. Figures on this page would be "
            "unreliable, so they have been withheld. Review `02_processed_data/data_quality_report.csv`, then "
            "re-run the refresh pipeline:"
        )
        st.code(REFRESH_COMMAND, language="bash")
        if stop_on_fail:
            st.stop()
