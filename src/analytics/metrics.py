import logging
import numpy as np
import pandas as pd
from config.settings import RISK_FREE_RATE_ANNUAL

logger = logging.getLogger(__name__)


def compute_risk_return_metrics(
    valid_tickers,
    daily_returns,
    n500_returns,
    n500_variance,
    n500_actual_return_annual,
    sector_returns_matrix,
    stock_metadata_map,
):
    """Calculates advanced risk/return metrics, alpha, beta, and Sharpe ratios

    aligned pairwise against Nifty 500 and sector benchmarks.
    """
    logger.info("Calculating advanced risk/return metrics...")

    results = []

    for stock in valid_tickers:
        if stock not in daily_returns.columns:
            continue

        meta = stock_metadata_map[stock]
        s_returns = daily_returns[stock].dropna()

        if len(s_returns) < 10:  # Skip stocks with insufficient trading history
            continue

        # 1-Year Return
        stock_ret_annual = (1 + s_returns).prod() - 1

        # Annualized Volatility
        volatility = daily_returns[stock].std() * np.sqrt(252)

        # Sharpe Ratio
        sharpe = (
            (stock_ret_annual - RISK_FREE_RATE_ANNUAL) / volatility
            if volatility > 0
            else np.nan
        )

        # --- CALCULATIONS VS NIFTY 500 (Pairwise Aligned) ---
        aligned_n500 = pd.concat([s_returns, n500_returns], axis=1).dropna()
        if len(aligned_n500) > 10 and n500_variance > 0:
            beta_n500 = (
                aligned_n500.iloc[:, 0].cov(aligned_n500.iloc[:, 1])
                / n500_variance
            )
            expected_ret_n500 = RISK_FREE_RATE_ANNUAL + beta_n500 * (
                n500_actual_return_annual - RISK_FREE_RATE_ANNUAL
            )
            alpha_n500 = stock_ret_annual - expected_ret_n500
        else:
            beta_n500, alpha_n500 = 1.0, 0.0

        # --- CALCULATIONS VS SECTOR BENCHMARK (Pairwise Aligned) ---
        sec_name = meta["Sector"]
        sec_series = sector_returns_matrix.get(sec_name, n500_returns).dropna()
        sec_variance = sec_series.var()
        sec_actual_return_annual = (1 + sec_series).prod() - 1

        aligned_sec = pd.concat([s_returns, sec_series], axis=1).dropna()
        if len(aligned_sec) > 10 and sec_variance > 0:
            beta_sector = (
                aligned_sec.iloc[:, 0].cov(aligned_sec.iloc[:, 1])
                / sec_variance
            )
            expected_ret_sector = RISK_FREE_RATE_ANNUAL + beta_sector * (
                sec_actual_return_annual - RISK_FREE_RATE_ANNUAL
            )
            alpha_sector = stock_ret_annual - expected_ret_sector
        else:
            beta_sector, alpha_sector = 1.0, 0.0

        # Distance from ATH
        ath = meta["ATH_Price"]
        curr_price = meta["Stock_Price"]
        ath_dist = (
            ((ath - curr_price) / ath) * 100
            if (
                not pd.isna(ath)
                and ath > 0
                and not pd.isna(curr_price)
            )
            else np.nan
        )

        results.append(
            {
                "Ticker": stock.replace(".NS", ""),
                "Sector": meta["Sector"],
                "Sector_Index_Symbol": meta["Sector_Index_Symbol"],
                "Industry": meta["Industry"],
                "Board_Based": meta["Board_Based"],
                "Index_Type": meta["Index_Type"],
                "Market_Cap_Tier": meta["Market_Cap_Tier"],
                "Upcoming_Event_Date": meta["Upcoming_Event_Date"],
                "Upcoming_Event_Name": meta["Upcoming_Event_Name"],
                "Stock_Price": meta["Stock_Price"],
                "ATH_Price": meta["ATH_Price"],
                "Distance_From_ATH_%": ath_dist,
                "Volatility_%": volatility * 100,
                "Sharpe_Ratio": sharpe,
                "Current_Qtr_Profit": meta["Current_Qtr_Profit"],
                "Max_Historic_Qtr_Profit": meta["Max_Historic_Qtr_Profit"],
                "Prev_Qtr1_Profit": meta["Prev_Qtr1_Profit"],
                "Prev_Qtr2_Profit": meta["Prev_Qtr2_Profit"],
                "Prev_Year_Profit": meta["Prev_Year_Profit"],
                "Stock_Year_Return": stock_ret_annual,
                "Nifty500_Year_Return": n500_actual_return_annual,
                "Sector_Year_Return": sec_actual_return_annual,
                "Nifty_Alpha": alpha_n500,
                "Sector_Alpha": alpha_sector,
                "TTM_Profit": meta["TTM_Profit"],
            }
        )

    return pd.DataFrame(results)


def grade_ath_price(row):
    """Grades proximity to All-Time High price (scale 1 to 5)."""
    if (
        pd.isna(row["Stock_Price"])
        or pd.isna(row["ATH_Price"])
        or row["ATH_Price"] == 0
    ):
        return 1
    distance = (1 - (row["Stock_Price"] / row["ATH_Price"])) * 100
    if distance <= 0:
        return 5
    elif distance <= 5:
        return 4
    elif distance <= 10:
        return 3
    elif distance <= 20:
        return 2
    else:
        return 1


def grade_ath_profit(row):
    """Grades quarterly profitability against historical maximums."""
    if pd.isna(row["Current_Qtr_Profit"]) or pd.isna(
        row["Max_Historic_Qtr_Profit"]
    ):
        return 1
    if row["Current_Qtr_Profit"] < 0:
        return 1
    elif row["Current_Qtr_Profit"] >= row["Max_Historic_Qtr_Profit"]:
        return 5
    elif row["Current_Qtr_Profit"] >= (0.90 * row["Max_Historic_Qtr_Profit"]):
        return 4
    elif (
        not pd.isna(row["Prev_Qtr1_Profit"])
        and not pd.isna(row["Prev_Qtr2_Profit"])
        and row["Current_Qtr_Profit"]
        > row["Prev_Qtr1_Profit"]
        > row["Prev_Qtr2_Profit"]
    ):
        return 3
    elif (
        not pd.isna(row["Prev_Year_Profit"])
        and row["Current_Qtr_Profit"] < row["Prev_Year_Profit"]
    ):
        return 2
    else:
        return 3


def assign_action_by_score(score):
    """Assigns trade actions (+ADD, HOLD, REVIEW, REPLACE, EXIT) based on score."""
    if pd.isna(score):
        return "EXIT"
    if score >= 3.75:
        return "+ADD"
    elif 3.15 <= score < 3.75:
        return "HOLD"
    elif 2.50 <= score < 3.15:
        return "REVIEW"
    elif 1.75 <= score < 2.50:
        return "REPLACE"
    else:
        return "EXIT"


def apply_grading_and_scoring_matrices(df_results):
    """Applies grading matrices, calculates review scores, and assigns portfolio actions."""
    logger.info("Applying grading and scoring matrices...")

    df_results["ATH_Price_Grade"] = df_results.apply(
        grade_ath_price, axis=1
    ).astype("Int64")
    df_results["ATH_Profit_Grade"] = df_results.apply(
        grade_ath_profit, axis=1
    ).astype("Int64")

    n500_pct = df_results["Nifty_Alpha"].rank(pct=True, method="first")
    df_results["Nifty_Alpha_Grade"] = np.ceil(n500_pct * 5).astype("Int64")

    sector_pct = df_results["Sector_Alpha"].rank(pct=True, method="first")
    df_results["Sector_Alpha_Grade"] = np.ceil(sector_pct * 5).astype("Int64")

    df_results["Alpha_Avg_Grade"] = (
        df_results["Nifty_Alpha_Grade"] + df_results["Sector_Alpha_Grade"]
    ) / 2

    df_results["Review_Score"] = (
        (df_results["ATH_Price_Grade"] * 0.50)
        + (df_results["ATH_Profit_Grade"] * 0.25)
        + (df_results["Nifty_Alpha_Grade"] * 0.15)
        + (df_results["Sector_Alpha_Grade"] * 0.10)
    )

    df_results["ACTION"] = df_results["Review_Score"].apply(
        assign_action_by_score
    )

    df_results = df_results.sort_values(
        by="Review_Score", ascending=False
    ).round(3)
    return df_results