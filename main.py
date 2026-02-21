"""Example orchestration for core trading logic.

This script demonstrates how strategy functions can be used with market/portfolio data.
API transport/authentication is intentionally omitted.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from strategy import check_buy_signal, execute_daily_liquidation, get_target_universe


def demo() -> None:
    market_data_df = pd.DataFrame(
        [
            {"Ticker": "005930", "Close": 77000, "Volume": 10_000_000, "MA20": 76000},
            {"Ticker": "035420", "Close": 195000, "Volume": 2_200_000, "MA20": 190000},
            {"Ticker": "068270", "Close": 171000, "Volume": 1_000_000, "MA20": 172000},
            {"Ticker": "247540", "Close": 40200, "Volume": 3_500_000, "MA20": 39000},
        ]
    )

    universe = get_target_universe(market_data_df)
    print("target_universe:", universe)

    sample_ohlcv = pd.DataFrame(
        [
            {"Open": 39000, "High": 41000, "Low": 38500, "Close": 40000},  # yesterday
            {"Open": 40100, "High": 42000, "Low": 39800, "Close": 41500},  # today
        ]
    )
    buy_signal = check_buy_signal("247540", sample_ohlcv)
    print("buy_signal:", buy_signal)

    current_portfolio = [
        {"ticker": "005930", "qty": 5},
        {"ticker": "247540", "qty": 20},
    ]
    sell_intents = execute_daily_liquidation(
        current_portfolio=current_portfolio,
        now_kst=datetime(2025, 1, 1, 15, 20),
    )
    print("sell_intents:", sell_intents)


if __name__ == "__main__":
    demo()
