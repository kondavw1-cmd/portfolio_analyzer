import numpy as np
import pandas as pd
import yfinance as yf
from tqdm import tqdm
import logging
from config.settings import BENCHMARK_TICKER, CHUNK_SIZE, SECTOR_INDEX_MAP
from src.utils.helpers import get_market_cap_tier_inr, parse_upcoming_event


logger = logging.getLogger(__name__)

def fetch_metadata_single(symbol: str, ticker_to_board_map: dict):
    """Fetches metadata, prices, and financial statements for a single ticker

    sequentially using standard yfinance.
    """
    ticker_obj = yf.Ticker(symbol)
    info = ticker_obj.info

    # Handle empty data
    if not info or not isinstance(info, dict) or len(info) <= 1:
        return symbol, None

    sector_name = (
        info.get("sector", "MISCELLANEOUS").upper().replace(" ", "_")
    )
    industry_name = (
        info.get("industry", "Other Financial Services")
        .upper()
        .replace(" ", "_")
    )
    mcap_raw = info.get("marketCap")
    mcap_tier = get_market_cap_tier_inr(mcap_raw)

    # Map Sector Index Symbol
    sector_index_symbol = SECTOR_INDEX_MAP.get(sector_name, "^CRSLDX")
    board_based_label = ticker_to_board_map.get(
        symbol, "NIFTY TOTAL MARKET"
    )

    try:
        calendar_data = ticker_obj.calendar
    except Exception:
        calendar_data = None

    event_dt, event_lbl = parse_upcoming_event(calendar_data)

    # Extract Current Price
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    stock_price = float(price) if price is not None else np.nan

    # Extract All-Time High (ATH) Price
    try:
        hist_max = ticker_obj.history(period="max")
        ath_price = (
            float(hist_max["High"].max())
            if (hist_max is not None and not hist_max.empty)
            else np.nan
        )
    except Exception:
        ath_price = np.nan

    # Initialize financial metrics as NaN
    max_hist_qtr, curr_qtr, prev_qtr1, prev_qtr2, prev_yr, ttm_prof = [
        np.nan
    ] * 6

    # 1. Quarterly financial segment extraction
    try:
        q_financials = ticker_obj.quarterly_financials
        if q_financials is not None and not q_financials.empty:
            possible_keys = [
                "Net Income Including Noncontrolling Interests",
                "Net Income",
                "Net Income Common Stockholders",
                "Net Income From Continuing Operation Net Minority Interest",
            ]

            net_income_series = None
            for key in possible_keys:
                if key in q_financials.index:
                    net_income_series = q_financials.loc[key]
                    break

            if net_income_series is not None and len(net_income_series) > 0:
                net_income_series = pd.to_numeric(
                    net_income_series, errors="coerce"
                )
                max_hist_qtr = float(net_income_series.max()) / 10000000
                curr_qtr = (
                    float(net_income_series.iloc[0]) / 10000000
                    if len(net_income_series) > 0
                    else np.nan
                )
                prev_qtr1 = (
                    float(net_income_series.iloc[1]) / 10000000
                    if len(net_income_series) > 1
                    else np.nan
                )
                prev_qtr2 = (
                    float(net_income_series.iloc[2]) / 10000000
                    if len(net_income_series) > 2
                    else np.nan
                )
    except Exception:
        pass

    # 2. Annual profit data extraction segment
    try:
        annual_financials = ticker_obj.financials
        if annual_financials is not None and not annual_financials.empty:
            annual_keys = [
                "Net Income",
                "Net Income Including Noncontrolling Interests",
            ]
            for key in annual_keys:
                if key in annual_financials.index:
                    series = pd.to_numeric(
                        annual_financials.loc[key], errors="coerce"
                    )
                    if len(series) > 0:
                        prev_yr = float(series.iloc[0]) / 10000000
                        break
    except Exception:
        pass

    # 3. Trailing Twelve Month data segment
    try:
        if (
            hasattr(ticker_obj, "ttm_financials")
            and ticker_obj.ttm_financials is not None
            and not ticker_obj.ttm_financials.empty
        ):
            ttm_keys = [
                "Net Income Including Noncontrolling Interests",
                "Net Income",
            ]
            for key in ttm_keys:
                if key in ticker_obj.ttm_financials.index:
                    series = pd.to_numeric(
                        ticker_obj.ttm_financials.loc[key], errors="coerce"
                    )
                    if len(series) > 0:
                        ttm_prof = float(series.iloc[0] / 10000000)
                        break
    except Exception:
        pass

    return symbol, {
        "Sector": sector_name,
        "Sector_Index_Symbol": sector_index_symbol,
        "Industry": industry_name,
        "Board_Based": board_based_label,
        "Index_Type": (
            "Benchmark" if sector_index_symbol == "^CRSLDX" else "Sectoral"
        ),
        "Market_Cap_Tier": mcap_tier,
        "Upcoming_Event_Date": event_dt,
        "Upcoming_Event_Name": event_lbl,
        "Stock_Price": stock_price,
        "ATH_Price": ath_price,
        "Max_Historic_Qtr_Profit": max_hist_qtr,
        "Current_Qtr_Profit": curr_qtr,
        "Prev_Qtr1_Profit": prev_qtr1,
        "Prev_Qtr2_Profit": prev_qtr2,
        "Prev_Year_Profit": prev_yr,
        "TTM_Profit": ttm_prof,
    }


def process_universe_metadata(raw_tickers: list, ticker_to_board_map: dict):
    """Iterates through the raw ticker universe sequentially to retrieve metadata

    and financial statements with error handling.
    """
    logger.info("\nRetrieving metadata, prices, and financial statements...")
    stock_sector_map = {}
    stock_metadata_map = {}
    valid_tickers = []

    # Simple, clean loop. No retries, no session rotation, no threading.
    for symbol in tqdm(raw_tickers, desc="Processing Tickers"):
        try:
            result = fetch_metadata_single(symbol, ticker_to_board_map)

            if result is not None:
                sym, meta = result
                if meta is not None:
                    stock_sector_map[sym] = meta["Sector"]
                    stock_metadata_map[sym] = meta
                    valid_tickers.append(sym)

        except Exception as e:
            logger.info(f"\n[Skipping] {symbol} - Error: {e}")

    # Verification block
    logger.info("\n--- Processing Complete ---")
    logger.info(f"Original Tickers Count: {len(raw_tickers)}")
    logger.info(f"Successfully Processed Tickers: {len(valid_tickers)}")

    if not valid_tickers:
        raise ValueError("No valid tickers were successfully processed.")

    return valid_tickers, stock_sector_map, stock_metadata_map


def download_historical_data_and_compute_returns(
    valid_tickers: list, stock_sector_map: dict
):
    """Downloads 1 year of daily historical prices in chunks, computes returns,

    benchmark variance, and sector return matrices.
    """
    logger.info(
        f"\nDownloading 1 year of daily historical prices in chunks of {CHUNK_SIZE}..."
    )

    chunk_dfs = []

    # Download Benchmark Index first to establish the master timeline
    logger.info("Downloading benchmark index...")
    benchmark_df = yf.download(
        BENCHMARK_TICKER, period="1y", progress=False
    )["Close"]
    if isinstance(benchmark_df, pd.Series):
        benchmark_df = benchmark_df.to_frame(name=BENCHMARK_TICKER)
    benchmark_df = benchmark_df.ffill().bfill()
    chunk_dfs.append(benchmark_df)

    # Download stocks in chunks to prevent cross-ticker NaN contamination
    for i in tqdm(
        range(0, len(valid_tickers), CHUNK_SIZE), desc="Downloading Stock Chunks"
    ):
        chunk = valid_tickers[i : i + CHUNK_SIZE]
        try:
            chunk_raw = yf.download(chunk, period="1y", progress=False)["Close"]
            if isinstance(chunk_raw, pd.Series):
                chunk_raw = chunk_raw.to_frame(name=chunk[0])

            chunk_cleaned = chunk_raw.ffill().bfill()
            chunk_dfs.append(chunk_cleaned)
        except Exception as e:
            logger.info(
                f"\n[Warning] Failed to download chunk starting at index {i}: {e}"
            )

    # Combine all cleaned chunks along columns (Outer Join)
    raw_data = pd.concat(chunk_dfs, axis=1, sort=True)
    raw_data = raw_data.ffill().bfill()

    # Calculate daily returns
    daily_returns = raw_data.pct_change()

    n500_returns = daily_returns[BENCHMARK_TICKER].dropna()
    n500_variance = n500_returns.var()
    n500_actual_return_annual = (1 + n500_returns).prod() - 1

    # Generate synthetic baseline tracks for each isolated sector
    unique_sectors = set(stock_sector_map.values())
    sector_returns_matrix = {}
    for sec in unique_sectors:
        sec_stocks = [
            s
            for s, sn in stock_sector_map.items()
            if sn == sec and s in daily_returns.columns
        ]
        if sec_stocks:
            sector_returns_matrix[sec] = daily_returns[sec_stocks].mean(
                axis=1, skipna=True
            )
        else:
            sector_returns_matrix[sec] = n500_returns

    return (
        daily_returns,
        n500_returns,
        n500_variance,
        n500_actual_return_annual,
        sector_returns_matrix,
    )