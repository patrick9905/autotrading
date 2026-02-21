"""Core day-trading strategy logic for KIS OpenAPI integrations.

This module intentionally focuses on pure trading logic and order-intent generation.
It does not implement full API transport/authentication; those should be handled by a
separate broker/infrastructure layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

import pandas as pd


EXCLUDED_TICKERS = ["005930", "000660"]


@dataclass(frozen=True)
class BuySignalResult:
    """Result payload for volatility breakout checks."""

    ticker: str
    should_buy: bool
    target_buy_price: float
    current_price: float


@dataclass(frozen=True)
class SellOrderIntent:
    """Order-intent object used by execution layer (API adapter)."""

    ticker: str
    qty: int
    side: str = "sell"
    order_type: str = "market"


def _validate_market_data_columns(market_data_df: pd.DataFrame) -> None:
    required = {"Ticker", "Close", "Volume", "MA20"}
    missing = required.difference(market_data_df.columns)
    if missing:
        raise ValueError(f"market_data_df is missing required columns: {sorted(missing)}")


def _validate_ohlcv_columns(daily_ohlcv_df: pd.DataFrame) -> None:
    required = {"Open", "High", "Low", "Close"}
    missing = required.difference(daily_ohlcv_df.columns)
    if missing:
        raise ValueError(f"daily_ohlcv_df is missing required columns: {sorted(missing)}")


def get_target_universe(market_data_df: pd.DataFrame) -> list[str]:
    """Return top-10 tradable tickers by volume under trend filter.

    Rules:
    1) Exclude hardcoded long-term holdings from trading universe.
    2) Keep only symbols where Close > MA20.
    3) Sort by Volume descending and return top 10 tickers.

    Parameters
    ----------
    market_data_df:
        DataFrame with columns: Ticker, Close, Volume, MA20.

    Returns
    -------
    list[str]
        Up to 10 tickers that pass all filters.
    """
    _validate_market_data_columns(market_data_df)

    df = market_data_df.copy()
    df["Ticker"] = df["Ticker"].astype(str)

    filtered = df.loc[
        (~df["Ticker"].isin(EXCLUDED_TICKERS))
        & (pd.to_numeric(df["Close"], errors="coerce") > pd.to_numeric(df["MA20"], errors="coerce"))
    ]

    if filtered.empty:
        return []

    sorted_df = filtered.sort_values("Volume", ascending=False)
    return sorted_df["Ticker"].head(10).tolist()


def check_buy_signal(ticker: str, daily_ohlcv_df: pd.DataFrame) -> BuySignalResult:
    """Check Larry Williams volatility breakout buy condition.

    Formula
    -------
    range = yesterday_high - yesterday_low
    target_buy_price = today_open + (range * 0.5)

    Buy condition:
    current_price >= target_buy_price

    Notes
    -----
    - `daily_ohlcv_df` should contain at least 2 rows ordered by date ascending.
    - The last row is treated as "today", and the second-last row as "yesterday".
    """
    if not ticker:
        raise ValueError("ticker must be a non-empty string")
    if str(ticker) in EXCLUDED_TICKERS:
        return BuySignalResult(
            ticker=str(ticker),
            should_buy=False,
            target_buy_price=0.0,
            current_price=0.0,
        )

    _validate_ohlcv_columns(daily_ohlcv_df)
    if len(daily_ohlcv_df) < 2:
        raise ValueError("daily_ohlcv_df must have at least 2 rows (yesterday, today)")

    df = daily_ohlcv_df.copy()

    yesterday = df.iloc[-2]
    today = df.iloc[-1]

    yesterday_high = float(yesterday["High"])
    yesterday_low = float(yesterday["Low"])
    today_open = float(today["Open"])
    current_price = float(today["Close"])

    price_range = yesterday_high - yesterday_low
    target_buy_price = today_open + (price_range * 0.5)
    should_buy = current_price >= target_buy_price

    return BuySignalResult(
        ticker=str(ticker),
        should_buy=should_buy,
        target_buy_price=target_buy_price,
        current_price=current_price,
    )


def execute_daily_liquidation(
    current_portfolio: list[dict[str, Any]],
    now_kst: datetime | None = None,
) -> list[SellOrderIntent]:
    """Create full-quantity market sell intents at 15:15 KST for non-excluded holdings.

    This function does not submit orders. It only creates order intents for an external
    execution layer.

    Parameters
    ----------
    current_portfolio:
        List like [{'ticker': '...', 'qty': 10}].
    now_kst:
        Optional override timestamp for testing. If omitted, uses system time.

    Returns
    -------
    list[SellOrderIntent]
        Market sell intents for eligible positions.
    """
    current_time = (now_kst or datetime.now()).time()
    if current_time < time(15, 15):
        return []

    order_intents: list[SellOrderIntent] = []

    for position in current_portfolio:
        ticker = str(position.get("ticker", "")).strip()
        qty = int(position.get("qty", 0) or 0)

        if not ticker or qty <= 0:
            continue

        # CRITICAL RULE: never place orders for excluded long-term holdings.
        if ticker in EXCLUDED_TICKERS:
            continue

        order_intents.append(SellOrderIntent(ticker=ticker, qty=qty))

    return order_intents
