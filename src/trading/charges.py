from typing import Dict, Union


def calculate_zerodha_charges(
    buy_price: float,
    sell_price: float,
    qty: float,
    segment: str = "intraday",
    exchange: str = "NSE",
) -> Dict[str, Union[float, Dict[str, float]]]:
    """Calculates exact Zerodha charges, taxes, and net P&L for Equity Delivery and Intraday trades[cite: 2]."""
    buy_val = buy_price * qty
    sell_val = sell_price * qty
    turnover = buy_val + sell_val
    gross_pnl = sell_val - buy_val

    segment = segment.lower()
    exchange = exchange.upper()

    if segment == "delivery":
        buy_brokerage = 0.0
        sell_brokerage = 0.0
    elif segment == "intraday":
        buy_brokerage = min(20.0, buy_val * 0.0003)
        sell_brokerage = min(20.0, sell_val * 0.0003)
    else:
        raise ValueError("Invalid segment. Use 'delivery' or 'intraday'.")

    brokerage = round(buy_brokerage + sell_brokerage, 3)
    stt = (
        round((buy_val * 0.001) + (sell_val * 0.001), 3)
        if segment == "delivery"
        else round(sell_val * 0.00025, 3)
    )
    txn_rate = 0.0000297 if exchange == "NSE" else 0.0000375
    exchange_charges = round(turnover * txn_rate, 3)
    sebi_charges = round(turnover * 0.000001, 3)
    stamp_rate = 0.00015 if segment == "delivery" else 0.00003
    stamp_duty = round(buy_val * stamp_rate, 3)

    gst = round((brokerage + exchange_charges + sebi_charges) * 0.18, 3)
    dp_charges = 15.34 if segment == "delivery" else 0.0

    total_charges = round(
        brokerage
        + stt
        + exchange_charges
        + sebi_charges
        + stamp_duty
        + gst
        + dp_charges,
        3,
    )
    net_pnl = round(gross_pnl - total_charges, 3)
    breakeven = round(total_charges / qty, 3) if qty > 0 else 0.0

    return {
        "total_charges": total_charges,
        "gross_pnl": round(gross_pnl, 3),
        "net_pnl": net_pnl,
        "breakeven_per_share": breakeven,
        "breakdown": {
            "brokerage": brokerage,
            "stt": stt,
            "exchange_charges": exchange_charges,
            "sebi_charges": sebi_charges,
            "stamp_duty": stamp_duty,
            "gst": gst,
            "dp_charges": dp_charges,
        },
    }