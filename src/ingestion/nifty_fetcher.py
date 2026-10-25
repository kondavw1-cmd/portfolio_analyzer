import io
import urllib.request
import pandas as pd
import yfinance as yf
from tqdm import tqdm
import logging

logger = logging.getLogger(__name__)

def fetch_csv_with_fallbacks(urls, headers):
    """Tries to download a CSV from a list of fallback URLs[cite: 1]."""
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                csv_data = response.read().decode("utf-8")
            df = pd.read_csv(io.StringIO(csv_data))
            df.columns = df.columns.str.strip().str.upper()
            symbol_col = [col for col in df.columns if "SYMBOL" in col]
            if symbol_col:
                return (
                    df[symbol_col[0]]
                    .dropna()
                    .astype(str)
                    .str.strip()
                    .tolist()
                )
        except Exception:
            continue
    return None


def fetch_nifty_750_universe():
    """Downloads official constituent lists from NSE India with fallback logic[cite: 1]."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }

    url_map = {
        "NIFTY 50": [
            "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
            "https://www.nseindia.com/content/indices/ind_nifty50list.csv",
        ],
        "NIFTY NEXT 50": [
            "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv",
            "https://www.nseindia.com/content/indices/ind_niftynext50list.csv",
        ],
        "NIFTY MIDCAP 150": [
            "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
            "https://archives.nseindia.com/content/indices/ind_niftymidcap150_list.csv",
        ],
        "NIFTY SMALLCAP 250": [
            "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
            "https://archives.nseindia.com/content/indices/ind_niftysmallcap250_list.csv",
        ],
        "NIFTY MICROCAP 250": [
            "https://archives.nseindia.com/content/indices/ind_niftymicrocap250list.csv",
            "https://archives.nseindia.com/content/indices/ind_niftymicrocap_microcap250list.csv",
            "https://archives.nseindia.com/content/indices/ind_niftymicrocap250_list.csv",
        ],
        "NIFTY TOTAL MARKET": [
            "https://archives.nseindia.com/content/indices/ind_niftytotalmarketlist.csv",
            "https://archives.nseindia.com/content/indices/ind_nifty_totalmarketlist.csv",
        ],
    }

    ticker_to_board = {}
    classified_tickers = set()

    
    logger.info("Fetching Nifty Total Market (750 Stocks) constituents from NSE India...")
    for index_name in [
        "NIFTY 50",
        "NIFTY NEXT 50",
        "NIFTY MIDCAP 150",
        "NIFTY SMALLCAP 250",
    ]:
        symbols = fetch_csv_with_fallbacks(url_map[index_name], headers)
        if symbols:
            for sym in symbols:
                ticker = f"{sym}.NS"
                if ticker not in ticker_to_board:
                    ticker_to_board[ticker] = index_name
                    classified_tickers.add(ticker)
            logger.info(f"-> Successfully loaded {len(symbols)} tickers for {index_name}")
        else:
            logger.info(f"[Warning] Failed to fetch {index_name}")

    total_market_symbols = fetch_csv_with_fallbacks(
        url_map["NIFTY TOTAL MARKET"], headers
    )
    microcap_symbols = fetch_csv_with_fallbacks(
        url_map["NIFTY MICROCAP 250"], headers
    )

    if total_market_symbols:
        logger.info(f"-> Successfully loaded {len(total_market_symbols)} tickers for NIFTY TOTAL MARKET")
        deduced_microcap_count = 0
        for sym in total_market_symbols:
            ticker = f"{sym}.NS"
            if ticker not in classified_tickers:
                ticker_to_board[ticker] = "NIFTY MICROCAP 250"
                classified_tickers.add(ticker)
                deduced_microcap_count += 1
        logger.info(f"-> Deduced {deduced_microcap_count} tickers for NIFTY MICROCAP 250 via Total Market subtraction.")
    elif microcap_symbols:
        for sym in microcap_symbols:
            ticker = f"{sym}.NS"
            if ticker not in classified_tickers:
                ticker_to_board[ticker] = "NIFTY MICROCAP 250"
                classified_tickers.add(ticker)
        logger.info(f"-> Loaded {len(microcap_symbols)} tickers for NIFTY MICROCAP 250 directly.")
    else:
        logger.info("[Error] Critical failure: Could not fetch Total Market or Microcap 250 lists.")

    all_tickers = list(classified_tickers)
    logger.info(f"Total unique tickers loaded: {len(all_tickers)}\n")
    return all_tickers, ticker_to_board