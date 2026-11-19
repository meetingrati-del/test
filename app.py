from __future__ import annotations

from datetime import date, timedelta
from io import BytesIO, StringIO
import re
import zipfile

import pandas as pd
import streamlit as st
import yfinance as yf


st.set_page_config(page_title="Equity Historical Data Downloader", page_icon="📈", layout="wide")
st.title("Equity Historical Data Downloader")
st.write("Upload a CSV containing a **symbol** column, choose a date range and interval, then download one CSV per symbol.")

uploaded_file = st.file_uploader("Upload symbols CSV", type=["csv"])

with st.form("download_options"):
    start_date = st.date_input("Start date", value=date.today() - timedelta(days=365))
    end_date = st.date_input("End date", value=date.today())
    interval_label = st.selectbox("Timeframe", ["Daily", "Weekly", "Monthly"])
    submitted = st.form_submit_button("Fetch historical data")

intervals = {"Daily": "1d", "Weekly": "1wk", "Monthly": "1mo"}


def safe_filename(symbol: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", symbol.strip())
    return cleaned.strip("._") or "symbol"


def csv_bytes(frame: pd.DataFrame) -> bytes:
    output = StringIO()
    frame.to_csv(output, index=True, index_label="Date")
    return output.getvalue().encode("utf-8-sig")


if submitted:
    if uploaded_file is None:
        st.error("Upload a CSV file first.")
    elif start_date > end_date:
        st.error("Start date must be on or before end date.")
    else:
        try:
            symbols_frame = pd.read_csv(uploaded_file)
            symbol_column = next((col for col in symbols_frame.columns if str(col).strip().lower() == "symbol"), None)
            if symbol_column is None:
                st.error('The uploaded CSV must contain a column named "symbol".')
            else:
                symbols = (
                    symbols_frame[symbol_column]
                    .dropna()
                    .astype(str)
                    .str.strip()
                )
                # Treat symbols without an exchange suffix as NSE tickers.
                symbols = [
                    symbol if "." in symbol else f"{symbol}.NS"
                    for symbol in symbols
                    if symbol
                ]
                symbols = list(dict.fromkeys(symbols))
                if not symbols:
                    st.error('The "symbol" column does not contain any symbols.')
                else:
                    results: dict[str, pd.DataFrame] = {}
                    failures: dict[str, str] = {}
                    progress = st.progress(0, text="Starting downloads...")
                    for index, symbol in enumerate(symbols, start=1):
                        try:
                            data = yf.download(
                                symbol,
                                start=start_date.isoformat(),
                                end=(end_date + timedelta(days=1)).isoformat(),
                                interval=intervals[interval_label],
                                auto_adjust=False,
                                progress=False,
                                threads=False,
                            )
                            if data is None or data.empty:
                                failures[symbol] = "No historical data was returned for this date range."
                            else:
                                # yfinance may return a two-level column index, even for a single ticker.
                                if isinstance(data.columns, pd.MultiIndex):
                                    data.columns = data.columns.get_level_values(0)
                                data.index.name = "Date"
                                results[symbol] = data
                        except Exception as exc:
                            failures[symbol] = str(exc)
                        progress.progress(index / len(symbols), text=f"Processed {index} of {len(symbols)} symbols")

                    st.session_state["download_results"] = results
                    st.session_state["download_failures"] = failures
                    st.session_state["download_interval"] = interval_label
        except Exception as exc:
            st.error(f"Could not read the uploaded CSV: {exc}")

results = st.session_state.get("download_results", {})
failures = st.session_state.get("download_failures", {})

if results:
    st.subheader("Download results")
    st.success(f"Retrieved data for {len(results)} symbol(s). Each symbol is available as its own CSV.")

    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for symbol, data in results.items():
            archive.writestr(f"{safe_filename(symbol)}.csv", csv_bytes(data))
    archive_buffer.seek(0)
    st.download_button(
        "Download all CSVs as ZIP",
        data=archive_buffer.getvalue(),
        file_name="equity_historical_data.zip",
        mime="application/zip",
        key="download_all_zip",
    )

    for symbol, data in results.items():
        filename = f"{safe_filename(symbol)}.csv"
        with st.expander(f"{symbol} · {len(data)} rows", expanded=False):
            st.dataframe(data.tail(10), use_container_width=True)
            st.download_button(
                f"Download {filename}",
                data=csv_bytes(data),
                file_name=filename,
                mime="text/csv",
                key=f"download_{safe_filename(symbol)}",
            )

if failures:
    st.subheader("Symbols without data")
    for symbol, reason in failures.items():
        st.warning(f"{symbol}: {reason}")




