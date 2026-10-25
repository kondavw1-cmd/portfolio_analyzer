import collections
from typing import Dict, Union
import pandas as pd
import yfinance as yf


def calculate_zerodha_charges(
    buy_price: float,
    sell_price: float,
    qty: float,
    segment: str = 'intraday',
    exchange: str = 'NSE'
) -> Dict[str, Union[float, Dict[str, float]]]:
    """
    Calculates exact Zerodha charges, taxes, and net P&L for Equity Delivery and Intraday trades.
    """
    buy_val = buy_price * qty
    sell_val = sell_price * qty
    turnover = buy_val + sell_val
    gross_pnl = sell_val - buy_val

    segment = segment.lower()
    exchange = exchange.upper()

    # 1. Brokerage Calculation
    if segment == 'delivery':
        buy_brokerage = 0.0
        sell_brokerage = 0.0
    elif segment == 'intraday':
        buy_brokerage = min(20.0, buy_val * 0.0003)
        sell_brokerage = min(20.0, sell_val * 0.0003)
    else:
        raise ValueError("Invalid segment. Use 'delivery' or 'intraday'.")

    brokerage = round(buy_brokerage + sell_brokerage, 3)

    # 2. Securities Transaction Tax (STT)
    if segment == 'delivery':
        stt = (buy_val * 0.001) + (sell_val * 0.001)
    else:
        stt = sell_val * 0.00025

    stt = round(stt, 3)

    # 3. Exchange Transaction Charges
    txn_rate = 0.0000297 if exchange == 'NSE' else 0.0000375
    exchange_charges = round(turnover * txn_rate, 3)

    # 4. SEBI Turnover Charges
    sebi_charges = round(turnover * 0.000001, 3)

    # 5. Stamp Duty (Buy side only)
    stamp_rate = 0.00015 if segment == 'delivery' else 0.00003
    stamp_duty = round(buy_val * stamp_rate, 3)

    # 6. Goods and Services Tax (GST)
    gst_taxable_value = brokerage + exchange_charges + sebi_charges
    gst = round(gst_taxable_value * 0.18, 3)

    # 7. DP Charges (Depository Participant Charges - Sell side delivery only)
    dp_charges = 15.34 if segment == 'delivery' else 0.0

    # Total Charges Calculation
    total_charges = round(
        brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst + dp_charges,
        3
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
            "dp_charges": dp_charges
        }
    }


def _format_holding_duration(delta) -> str:
    """Formats timedelta into 'X days X hours'."""
    if pd.isna(delta):
        return ''
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        total_seconds = 0
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    return f"{days} days {hours} hours"


def _parse_trade_batches(csv_filepath: str) -> list:
    """Shared helper to parse CSV and run FIFO matching."""
    df = pd.read_csv(csv_filepath)
    df.columns = df.columns.str.strip().str.lower()

    symbol_col = (
        'tradingsymbol' if 'tradingsymbol' in df.columns else 'symbol'
    )
    type_col = 'trade_type' if 'trade_type' in df.columns else 'buy_sell'
    time_col = (
        'order_execution_time'
        if 'order_execution_time' in df.columns
        else 'trade_date'
    )

    df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
    df = df.sort_values(by=time_col).reset_index(drop=True)

    trade_batches = []
    batch_counter = 0
    open_batches = collections.defaultdict(collections.deque)

    for _, row in df.iterrows():
        symbol = row[symbol_col]
        t_type = str(row[type_col]).strip().lower()
        qty = float(row['quantity'])
        price = float(row['price'])
        timestamp = row[time_col]

        is_buy = t_type in ['buy', 'b', 'purchase']

        if is_buy:
            batch = {
                'batch_id': batch_counter,
                'symbol': symbol,
                'entry_time': timestamp,
                'buy_qty': qty,
                'remaining_qty': qty,
                'buy_price': price,
                'sold_qty': 0.0,
                'sell_revenue': 0.0,
                'exit_times': [],
            }
            batch_counter += 1
            trade_batches.append(batch)
            open_batches[symbol].append(batch)
        else:
            sell_qty_remaining = qty
            while sell_qty_remaining > 0 and open_batches[symbol]:
                batch = open_batches[symbol][0]
                matched_qty = min(sell_qty_remaining, batch['remaining_qty'])

                batch['sold_qty'] += matched_qty
                batch['remaining_qty'] -= matched_qty
                batch['sell_revenue'] += matched_qty * price
                batch['exit_times'].append(timestamp)

                sell_qty_remaining -= matched_qty
                if batch['remaining_qty'] == 0:
                    open_batches[symbol].popleft()

    return trade_batches


def process_closed_tradebook(
    csv_filepath: str, segment: str = 'intraday', exchange: str = 'NSE'
) -> pd.DataFrame:
    """Parses Zerodha tradebook and returns CLOSED and PARTIAL_CLOSED trades

    with fully realized P&L, exact regulatory charges, and rounded metrics.
    """
    trade_batches = _parse_trade_batches(csv_filepath)
    results = []

    for b in trade_batches:
        sold_qty = b['sold_qty']
        buy_qty = b['buy_qty']

        if sold_qty == 0:
            continue

        status = 'CLOSED' if sold_qty >= buy_qty else 'PARTIAL_CLOSED'
        effective_qty = sold_qty if status == 'PARTIAL_CLOSED' else buy_qty

        buy_price = b['buy_price']
        buy_value = round(effective_qty * buy_price, 3)
        sell_value = round(b['sell_revenue'], 3)

        avg_sell_price = sell_value / effective_qty if effective_qty > 0 else 0.0
        
        charge_result = calculate_zerodha_charges(
            buy_price=buy_price,
            sell_price=avg_sell_price,
            qty=effective_qty,
            segment=segment,
            exchange=exchange
        )

        net_pnl = charge_result['net_pnl']
        net_pnl_pct = (
            round((net_pnl / buy_value) * 100, 3) if buy_value > 0 else 0.0
        )

        entry_time = b['entry_time']
        exit_time = max(b['exit_times']) if b['exit_times'] else pd.NaT
        holding_duration = _format_holding_duration(exit_time - entry_time) if pd.notna(exit_time) and pd.notna(entry_time) else ''

        entry_date_str = entry_time.strftime('%Y-%m-%d') if pd.notna(entry_time) else ''
        exit_date_str = exit_time.strftime('%Y-%m-%d') if pd.notna(exit_time) else ''

        results.append({
            'Instrument': b['symbol'],
            'Status': status,
            'Entry Date': entry_date_str,
            'Exit Date': exit_date_str,
            'Holding Duration': holding_duration,
            'Qty': int(effective_qty),
            'Avg. Buy Cost': round(buy_price, 3),
            'Avg. Sell Cost': round(avg_sell_price, 3),
            'Buy Value': buy_value,
            'Sell Value': sell_value,
            'Gross PnL': round(charge_result['gross_pnl'], 3),
            'Total Charges': round(charge_result['total_charges'], 3),
            'Net PnL': round(net_pnl, 3),
            'Net PnL Pct': round(net_pnl_pct, 3),
        })

    return pd.DataFrame(results)


def process_open_partial_tradebook(
    csv_filepath: str,
    total_capital: float = 150000.0,
    allocation_pct: float = 0.065
) -> pd.DataFrame:
    """Parses Zerodha tradebook, keeps open/partial batches separate per row,

    calculates allocation and risk metrics based on aggregated symbol-level totals,
    and fetches live LTP and previous close via yfinance[cite: 1].
    """
    trade_batches = _parse_trade_batches(csv_filepath)

    # 1. Aggregate open quantities and total cost per unique symbol for portfolio metrics
    symbol_aggregates = collections.defaultdict(lambda: {
        'total_qty': 0.0,
        'total_cost': 0.0
    })

    symbols_to_fetch = set()
    for b in trade_batches:
        remaining_qty = b['remaining_qty']
        if remaining_qty > 0:
            symbol = b['symbol']
            symbols_to_fetch.add(symbol)
            symbol_aggregates[symbol]['total_qty'] += remaining_qty
            symbol_aggregates[symbol]['total_cost'] += remaining_qty * b['buy_price']

    if not symbols_to_fetch:
        return pd.DataFrame(columns=[
            'Instrument', 'status', 'entry_time', 'holding_duration', 
            'Qty.', 'Avg. cost', 'LTP', 'Invested', 'Cur. val', 'P&L', 
            'Net chg.', 'Day chg.', 'Allowed Investment', 'Allowed Shares', 
            'Invested Allocation %', 'Current Value Allocation %', 'Defined SL [RISK]'
        ])

    # Map symbols to Yahoo Finance tickers (defaulting to .NS for NSE)
    ticker_map = {s: (s if '.' in s else f"{s}.NS") for s in symbols_to_fetch}
    tickers_list = list(set(ticker_map.values()))

    # Fetch live data via yfinance
    try:
        data = yf.download(tickers_list, period="2d", progress=False, group_by='ticker')
    except Exception:
        data = pd.DataFrame()

    # Cache price data per symbol
    symbol_price_data = {}
    for symbol in symbols_to_fetch:
        t_symbol = ticker_map[symbol]
        ltp = None
        prev_close = None
        try:
            if len(tickers_list) == 1:
                hist = yf.Ticker(tickers_list[0]).history(period="2d")
                if not hist.empty:
                    ltp = float(hist['Close'].iloc[-1])
                    prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else ltp
            else:
                if t_symbol in data.columns.levels[0]:
                    hist = data[t_symbol].dropna(subset=['Close'])
                    if not hist.empty:
                        ltp = float(hist['Close'].iloc[-1])
                        prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else ltp
        except Exception:
            pass
        
        symbol_price_data[symbol] = {'ltp': ltp, 'prev_close': prev_close}

    # 2. Compute symbol-level aggregated metrics for Allowed Investment, Allocation, and SL [RISK]
    symbol_metrics = {}
    base_allowed_investment_per_stock = allocation_pct * total_capital

    for symbol, data_dict in symbol_aggregates.items():
        tot_qty = data_dict['total_qty']
        tot_cost = data_dict['total_cost']
        if tot_qty <= 0:
            continue

        avg_cost_sym = tot_cost / tot_qty
        p_data = symbol_price_data.get(symbol, {})
        ltp_sym = p_data.get('ltp')
        if ltp_sym is None:
            ltp_sym = avg_cost_sym

        invested_sym = round(tot_cost, 3)
        cur_val_sym = round(tot_qty * ltp_sym, 3)

        allowed_investment = round(base_allowed_investment_per_stock - invested_sym, 3)
        allowed_shares = int(allowed_investment / ltp_sym) if allowed_investment > 0 and ltp_sym > 0 else 0
        invested_allocation_pct = round((invested_sym / total_capital) * 100, 3)
        cur_val_allocation_pct = round((cur_val_sym / total_capital) * 100, 3)

        risk_amount = (total_capital * 0.01) / 2 if invested_sym < 6000 else (total_capital * 0.01)
        defined_sl = round(avg_cost_sym - (risk_amount / tot_qty), 3) if tot_qty > 0 else avg_cost_sym

        symbol_metrics[symbol] = {
            'Allowed Investment': allowed_investment,
            'Allowed Shares': allowed_shares,
            'Invested Allocation %': invested_allocation_pct,
            'Current Value Allocation %': cur_val_allocation_pct,
            'Defined SL [RISK]': defined_sl
        }

    # 3. Build rows for each individual open/partial batch while mapping symbol-level metrics
    results = []
    for b in trade_batches:
        remaining_qty = b['remaining_qty']
        if remaining_qty == 0:
            continue

        symbol = b['symbol']
        sold_qty = b['sold_qty']
        status = 'OPEN' if sold_qty == 0 else 'PARTIAL_OPEN'
        
        buy_price = b['buy_price']
        qty = int(remaining_qty)
        avg_cost = round(buy_price, 3)

        p_data = symbol_price_data.get(symbol, {})
        ltp = p_data.get('ltp')
        prev_close = p_data.get('prev_close')

        if ltp is None:
            ltp = avg_cost
        if prev_close is None:
            prev_close = ltp

        ltp = round(ltp, 3)
        prev_close = round(prev_close, 3)

        invested = round(qty * avg_cost, 3)
        cur_val = round(qty * ltp, 3)
        pnl = round(cur_val - invested, 3)

        net_chg_pct = round(((ltp - avg_cost) / avg_cost) * 100, 3) if avg_cost > 0 else 0.0
        day_chg_pct = round(((ltp - prev_close) / prev_close) * 100, 3) if prev_close > 0 else 0.0

        entry_time = b['entry_time']
        entry_date_str = entry_time.strftime('%Y-%m-%d') if pd.notna(entry_time) else ''
        holding_duration = _format_holding_duration(pd.Timestamp.now() - entry_time) if pd.notna(entry_time) else 'Open'

        metrics = symbol_metrics.get(symbol, {
            'Allowed Investment': 0.0,
            'Allowed Shares': 0,
            'Invested Allocation %': 0.0,
            'Current Value Allocation %': 0.0,
            'Defined SL [RISK]': avg_cost
        })

        results.append({
            'Instrument': symbol,
            'Status': status,
            'Entry Date': entry_date_str,
            'Holding Duration': holding_duration,
            'Qty.': qty,
            'Avg. cost': avg_cost,
            'LTP': ltp,
            'Invested': invested,
            'Cur. val': cur_val,
            'P&L': pnl,
            'Net chg.': net_chg_pct,
            'Day chg.': day_chg_pct,
            'Allowed Investment': metrics['Allowed Investment'],
            'Allowed Shares': metrics['Allowed Shares'],
            'Invested Allocation %': metrics['Invested Allocation %'],
            'Current Value Allocation %': metrics['Current Value Allocation %'],
            'Defined SL [RISK]': metrics['Defined SL [RISK]'],
        })

    return pd.DataFrame(results)