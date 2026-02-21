"""Korea Investment & Securities (KIS) OpenAPI handler for overseas stock trading.

This module focuses on NASDAQ trading and provides helper methods for:
- Access token management
- Quote lookup
- Cash balance lookup
- Overseas order placement
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class KISConfig:
    app_key: str
    app_secret: str
    account_no: str
    account_product_code: str
    base_url: str
    exchange_code: str = "NASD"  # NASDAQ


class KISAPIHandler:
    """Thin wrapper around KIS OpenAPI endpoints used by this project.

    Note:
    - Endpoint paths/TR IDs can differ between real and paper accounts.
    - Always validate against the latest KIS developer docs before live trading.
    """

    def __init__(self, config: KISConfig):
        self.config = config
        self._access_token: str | None = None
        self._token_expire_at: float = 0.0

    @classmethod
    def from_env(cls) -> "KISAPIHandler":
        config = KISConfig(
            app_key=os.environ["KIS_APP_KEY"],
            app_secret=os.environ["KIS_APP_SECRET"],
            account_no=os.environ["KIS_ACCOUNT_NO"],
            account_product_code=os.environ["KIS_ACCOUNT_PRODUCT_CODE"],
            base_url=os.environ.get("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443"),
            exchange_code=os.environ.get("KIS_EXCHANGE_CODE", "NASD"),
        )
        return cls(config)

    def _issue_access_token(self) -> None:
        url = f"{self.config.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        body = response.json()

        self._access_token = body["access_token"]
        expires_in = int(body.get("expires_in", 3600))
        self._token_expire_at = time.time() + max(expires_in - 60, 0)

    def _get_access_token(self) -> str:
        if self._access_token and time.time() < self._token_expire_at:
            return self._access_token
        self._issue_access_token()
        assert self._access_token is not None
        return self._access_token

    def _headers(self, tr_id: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._get_access_token()}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "tr_id": tr_id,
        }

    def get_overseas_price(self, symbol: str) -> float:
        """Return latest price for an overseas symbol."""
        url = f"{self.config.base_url}/uapi/overseas-price/v1/quotations/price"
        params = {
            "AUTH": "",
            "EXCD": self.config.exchange_code,
            "SYMB": symbol,
        }
        response = requests.get(
            url,
            headers=self._headers(tr_id="HHDFS00000300"),
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
        output = body.get("output", {})
        price = output.get("last") or output.get("stck_prpr")
        if price is None:
            raise ValueError(f"Price field missing for symbol={symbol}: {body}")
        return float(price)

    def get_available_usd(self) -> float:
        """Get available USD buying power for overseas stocks."""
        url = f"{self.config.base_url}/uapi/overseas-stock/v1/trading/inquire-psamount"
        params = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "OVRS_EXCG_CD": self.config.exchange_code,
            "OVRS_ORD_UNPR": "1",
            "ITEM_CD": "AAPL",  # API requires a valid symbol for query context
        }
        response = requests.get(
            url,
            headers=self._headers(tr_id="TTTS3007R"),
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        body = response.json()
        output = body.get("output", {})
        amount = output.get("ovrs_ord_psbl_amt") or output.get("ord_psbl_cash")
        if amount is None:
            raise ValueError(f"USD balance field missing: {body}")
        return float(amount)

    def place_overseas_order(self, symbol: str, quantity: int, side: str = "buy") -> dict[str, Any]:
        """Place a market-like order (limit with current price for compatibility)."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        current_price = self.get_overseas_price(symbol)
        tr_id = "TTTT1002U" if side.lower() == "buy" else "TTTT1006U"
        url = f"{self.config.base_url}/uapi/overseas-stock/v1/trading/order"
        payload = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "OVRS_EXCG_CD": self.config.exchange_code,
            "PDNO": symbol,
            "ORD_QTY": str(quantity),
            "OVRS_ORD_UNPR": str(round(current_price, 2)),
            "ORD_SVR_DVSN_CD": "0",
            "ORD_DVSN": "00",  # limit-like
        }
        response = requests.post(url, headers=self._headers(tr_id=tr_id), json=payload, timeout=10)
        response.raise_for_status()
        return response.json()
