import warnings

# Suppress all inplace keyword deprecation warnings globally across external libraries like yfinance
warnings.filterwarnings(
    "ignore", category=Warning, message=".*inplace keyword.*"
)  # wait, change "action" to "ignore"
warnings.filterwarnings(
    "ignore", category=Warning, message=".*inplace keyword.*"
)

import logging
import os
import shutil
import pandas as pd

from config.settings import (
    ALLOCATION_PCT,
    OUTPUT_EXCEL_FILE,
    TEMP_AVG_COST_OF_750_STOCKS,
    TEMP_ENTRY_DATE,
    TOTAL_CAPITAL,
)
from src.analytics.metrics import (
    apply_grading_and_scoring_matrices,
    compute_risk_return_metrics,
)
from src.ingestion.market_data import (
    download_historical_data_and_compute_returns,
    process_universe_metadata,
)
from src.ingestion.nifty_fetcher import fetch_nifty_750_universe
from src.trading.tradebook import (
    process_closed_tradebook,
    process_open_partial_tradebook,
)
from src.utils.database import (
    load_dataframe_from_db,
    save_dataframe_to_db,
)
from src.utils.helpers import (
    build_universe_750_scores_df,
    enrich_closed_journal_df,
    enrich_open_journal_df,
    export_to_excel_direct,
)

logger = logging.getLogger(__name__)

# Checkpoint file paths
CACHE_DIR = "data/cache"
UNIVERSE_CACHE = os.path.join(CACHE_DIR, "checkpoint_universe.pkl")
METADATA_CACHE = os.path.join(CACHE_DIR, "checkpoint_metadata.pkl")
RETURNS_CACHE = os.path.join(CACHE_DIR, "checkpoint_returns.pkl")
SCORES_CACHE = os.path.join(CACHE_DIR, "checkpoint_scored_results.csv")


def main():
    logger.info("=== Initializing Modular Portfolio Analyzer & Tradebook Engine ===")

    # Create cache directory and verify existence
    os.makedirs(CACHE_DIR, exist_ok=True)
    assert os.path.isdir(CACHE_DIR), f"Cache directory '{CACHE_DIR}' failed to initialize."
    logger.info(f"Verified cache directory is ready at: {os.path.abspath(CACHE_DIR)}")

    try:
        # =====================================================================
        # Step 1. Fetch Nifty 750 Universe & Board Map (with Checkpoint)
        # =====================================================================
        if os.path.exists(UNIVERSE_CACHE):
            logger.info("[Checkpoint] Loading Nifty 750 universe from cache...")
            universe_cache_df = pd.read_pickle(UNIVERSE_CACHE)
            raw_tickers = universe_cache_df["raw_tickers"].tolist()
            ticker_to_board_map = universe_cache_df["ticker_to_board_map"].iloc[0]
        else:
            logger.info("Fetching Nifty 750 universe from live sources...")
            raw_tickers, ticker_to_board_map = fetch_nifty_750_universe()
            raw_tickers = list(dict.fromkeys(raw_tickers)) + [
                "MANINDS.NS",
                "MANINDS.NS",
                "SSWL.NS",
                "TFCILTD.NS",
            ]
            pd.to_pickle(
                pd.DataFrame(
                    {
                        "raw_tickers": [raw_tickers],
                        "ticker_to_board_map": [ticker_to_board_map],
                    }
                ),
                UNIVERSE_CACHE,
            )
            logger.info("[Checkpoint] Saved universe checkpoint.")

        # =====================================================================
        # Step 2. Process Metadata & Financial Statements (with Checkpoint)
        # =====================================================================
        if os.path.exists(METADATA_CACHE):
            logger.info("[Checkpoint] Loading metadata and financial statements from cache...")
            meta_cache_df = pd.read_pickle(METADATA_CACHE)
            valid_tickers = meta_cache_df["valid_tickers"].iloc[0]
            stock_sector_map = meta_cache_df["stock_sector_map"].iloc[0]
            stock_metadata_map = meta_cache_df["stock_metadata_map"].iloc[0]
        else:
            logger.info("Processing metadata & financial statements...")
            valid_tickers, stock_sector_map, stock_metadata_map = (
                process_universe_metadata(raw_tickers, ticker_to_board_map)
            )
            pd.to_pickle(
                pd.DataFrame(
                    {
                        "valid_tickers": [valid_tickers],
                        "stock_sector_map": [stock_sector_map],
                        "stock_metadata_map": [stock_metadata_map],
                    }
                ),
                METADATA_CACHE,
            )
            logger.info("[Checkpoint] Saved metadata checkpoint.")

        # =====================================================================
        # Step 3. Download Historical Data & Compute Returns (with Checkpoint)
        # =====================================================================
        if os.path.exists(RETURNS_CACHE):
            logger.info("[Checkpoint] Loading historical returns matrix from cache...")
            ret_cache_df = pd.read_pickle(RETURNS_CACHE)
            daily_returns = ret_cache_df["daily_returns"].iloc[0]
            n500_returns = ret_cache_df["n500_returns"].iloc[0]
            n500_variance = ret_cache_df["n500_variance"].iloc[0]
            n500_actual_return_annual = ret_cache_df[
                "n500_actual_return_annual"
            ].iloc[0]
            sector_returns_matrix = ret_cache_df["sector_returns_matrix"].iloc[0]
        else:
            logger.info("Downloading historical data and computing returns matrix...")
            (
                daily_returns,
                n500_returns,
                n500_variance,
                n500_actual_return_annual,
                sector_returns_matrix,
            ) = download_historical_data_and_compute_returns(
                valid_tickers, stock_sector_map
            )
            pd.to_pickle(
                pd.DataFrame(
                    {
                        "daily_returns": [daily_returns],
                        "n500_returns": [n500_returns],
                        "n500_variance": [n500_variance],
                        "n500_actual_return_annual": [
                            n500_actual_return_annual
                        ],
                        "sector_returns_matrix": [sector_returns_matrix],
                    }
                ),
                RETURNS_CACHE,
            )
            logger.info("[Checkpoint] Saved historical returns checkpoint.")

        # =====================================================================
        # Step 4 & 5. Dual Calculation, Grading, & Scoring (with Checkpoint)
        # =====================================================================
        if os.path.exists(SCORES_CACHE):
            logger.info("[Checkpoint] Loading scored results from cache...")
            df_scored_results = pd.read_csv(SCORES_CACHE)
        else:
            logger.info("Running risk/return calculation and grading engine...")
            df_results = compute_risk_return_metrics(
                valid_tickers=valid_tickers,
                daily_returns=daily_returns,
                n500_returns=n500_returns,
                n500_variance=n500_variance,
                n500_actual_return_annual=n500_actual_return_annual,
                sector_returns_matrix=sector_returns_matrix,
                stock_metadata_map=stock_metadata_map,
            )
            df_scored_results = apply_grading_and_scoring_matrices(df_results)
            df_scored_results.to_csv(SCORES_CACHE, index=False)
            logger.info("[Checkpoint] Saved scored results checkpoint.")

        # Filter out GOLDBEES from scored results
        df_scored_results = df_scored_results[
            ~df_scored_results["Ticker"].str.contains(
                "GOLDBEES", case=False, na=False
            )
        ]

        # =====================================================================
        # Step 6. Process Tradebook Journals & Enrich with Scores & Grades
        # =====================================================================
        tradebook_path = os.path.join("data", "tradebook-DIZ015-EQ.csv")
        open_journal_df = pd.DataFrame()
        closed_journal_df = pd.DataFrame()

        if os.path.exists(tradebook_path):
            logger.info(f"Processing tradebook data from {tradebook_path}...")
            raw_closed_journal = process_closed_tradebook(
                csv_filepath=tradebook_path, segment="delivery", exchange="NSE"
            )
            if raw_closed_journal is not None and not raw_closed_journal.empty:
                symbol_col = (
                    "symbol"
                    if "symbol" in raw_closed_journal.columns
                    else "Instrument"
                )
                raw_closed_journal = raw_closed_journal[
                    ~raw_closed_journal[symbol_col].str.contains(
                        "GOLDBEES", case=False, na=False
                    )
                ]
                closed_journal_df = enrich_closed_journal_df(
                    raw_closed_journal, df_scored_results
                )

            raw_open_journal = process_open_partial_tradebook(
                csv_filepath=tradebook_path,
                total_capital=TOTAL_CAPITAL,
                allocation_pct=ALLOCATION_PCT,
            )
            if raw_open_journal is not None and not raw_open_journal.empty:
                inst_col = (
                    "Instrument"
                    if "Instrument" in raw_open_journal.columns
                    else "symbol"
                )
                raw_open_journal = raw_open_journal[
                    ~raw_open_journal[inst_col].str.contains(
                        "GOLDBEES", case=False, na=False
                    )
                ]
                open_journal_df = enrich_open_journal_df(
                    raw_open_journal, df_scored_results
                )
        else:
            logger.warning(
                f"Tradebook CSV not found at '{tradebook_path}'. Skipping journals."
            )

        # =====================================================================
        # Step 7. Build Universe 750 Scores DataFrame
        # =====================================================================
        universe_750_df = build_universe_750_scores_df(
            df_scored_results=df_scored_results,
            temp_avg_cost_map=TEMP_AVG_COST_OF_750_STOCKS,
            temp_entry_date=TEMP_ENTRY_DATE,
            total_capital=TOTAL_CAPITAL,
            allocation_pct=ALLOCATION_PCT,
            open_journal_df=open_journal_df,
        )
        universe_750_df = universe_750_df[
            ~universe_750_df["Instrument"].str.contains(
                "GOLDBEES", case=False, na=False
            )
        ]

        # =====================================================================
        # Step 8. Save DataFrames to SQLite Database
        # =====================================================================
        logger.info("Persisting processed dataframes to SQLite database...")
        save_dataframe_to_db(universe_750_df, "universe_750_scores")
        save_dataframe_to_db(df_scored_results, "python_750_computed_scores")
        save_dataframe_to_db(open_journal_df, "open_partial_journal")
        save_dataframe_to_db(closed_journal_df, "closed_journal")

        # =====================================================================
        # Step 9. Read Data From SQLite Database for Export
        # =====================================================================
        logger.info("Reading data back from SQLite database for Excel export...")
        db_universe_df = load_dataframe_from_db("universe_750_scores")
        db_scored_df = load_dataframe_from_db("python_750_computed_scores")
        db_open_df = load_dataframe_from_db("open_partial_journal")
        db_closed_df = load_dataframe_from_db("closed_journal")

        # =====================================================================
        # Step 10. Export Data Read from DB to Multi-Tab Excel Report
        # =====================================================================
        export_to_excel_direct(
            output_path=OUTPUT_EXCEL_FILE,
            df_scored_results=db_scored_df,
            universe_750_df=db_universe_df,
            open_journal_df=db_open_df,
            closed_journal_df=db_closed_df,
        )

        logger.info("=== Execution Complete Successfully ===")

    except Exception as e:
        logger.error(f"[Error] Pipeline failed during execution: {e}", exc_info=True)
        raise

    finally:
        # Automatically clean up cache directory on successful completion
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
            logger.info("Successfully cleaned up intermediate cache directory: data/cache/")


if __name__ == "__main__":
    main()