"""Equity option pricer (European / American).

Methods:
  - Black-Scholes analytical (European)
  - Binomial tree (American)
  - QuantLib (optional cross-check)
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import norm

from app.greeks.calculator import GreeksCalculator
from app.pricing.base import BasePricer, PricingResult


class EquityOptionPricer(BasePricer):
    """Price equity options with multiple methods."""

    def __init__(
        self,
        spot: float,
        strike: float,
        maturity: float,
        vol: float,
        r_dom: float,
        dividend_yield: float = 0.0,
        option_type: str = "call",
        exercise_style: str = "european",
        notional: float = 1.0,
        currency: str = "USD",
    ):
        self.spot = spot
        self.strike = strike
        self.maturity = maturity
        self.vol = vol
        self.r_dom = r_dom
        self.dividend_yield = dividend_yield
        self.option_type = option_type.lower()
        self.exercise_style = exercise_style.lower()
        self.notional = notional
        self.currency = currency

    # ── validation ──────────────────────────────────────────────
    def validate_inputs(self) -> list[str]:
        errors: list[str] = []
        if self.spot <= 0:
            errors.append("spot must be > 0")
        if self.strike <= 0:
            errors.append("strike must be > 0")
        if self.maturity <= 0:
            errors.append("maturity must be > 0")
        if self.vol <= 0:
            errors.append("vol must be > 0")
        if self.option_type not in ("call", "put"):
            errors.append("option_type must be 'call' or 'put'")
        return errors

    # ── Black-Scholes analytical ────────────────────────────────
    def _d1_d2(self) -> tuple[float, float]:
        S, K, T, sigma, r, q = (
            self.spot, self.strike, self.maturity,
            self.vol, self.r_dom, self.dividend_yield,
        )
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return d1, d2

    def price_black_scholes(self) -> float:
        S, K, T, r, q = (
            self.spot, self.strike, self.maturity, self.r_dom, self.dividend_yield,
        )
        d1, d2 = self._d1_d2()

        if self.option_type == "call":
            price = (
                S * math.exp(-q * T) * norm.cdf(d1)
                - K * math.exp(-r * T) * norm.cdf(d2)
            )
        else:
            price = (
                K * math.exp(-r * T) * norm.cdf(-d2)
                - S * math.exp(-q * T) * norm.cdf(-d1)
            )
        return price * self.notional

    # ── Binomial tree (CRR) ─────────────────────────────────────
    def price_binomial(self, n_steps: int = 500) -> float:
        S, K, T, r, q, sigma = (
            self.spot, self.strike, self.maturity,
            self.r_dom, self.dividend_yield, self.vol,
        )
        dt = T / n_steps
        u = math.exp(sigma * math.sqrt(dt))
        d = 1 / u
        p = (math.exp((r - q) * dt) - d) / (u - d)
        disc = math.exp(-r * dt)

        # Terminal payoffs
        asset_prices = np.array([S * u**j * d**(n_steps - j) for j in range(n_steps + 1)])
        if self.option_type == "call":
            values = np.maximum(asset_prices - K, 0.0)
        else:
            values = np.maximum(K - asset_prices, 0.0)

        # Backward induction
        for i in range(n_steps - 1, -1, -1):
            asset_prices = np.array([S * u**j * d**(i - j) for j in range(i + 1)])
            continuation = disc * (p * values[1:i+2] + (1 - p) * values[0:i+1])

            if self.exercise_style == "american":
                if self.option_type == "call":
                    intrinsic = np.maximum(asset_prices - K, 0.0)
                else:
                    intrinsic = np.maximum(K - asset_prices, 0.0)
                values = np.maximum(continuation, intrinsic)
            else:
                values = continuation

        return float(values[0]) * self.notional

    # ── BS analytical Greeks ────────────────────────────────────
    def bs_greeks(self) -> dict[str, float]:
        S, K, T, sigma, r, q = (
            self.spot, self.strike, self.maturity,
            self.vol, self.r_dom, self.dividend_yield,
        )
        d1, d2 = self._d1_d2()
        sqrt_T = math.sqrt(T)

        if self.option_type == "call":
            delta = math.exp(-q * T) * norm.cdf(d1)
            theta = (
                -S * norm.pdf(d1) * sigma * math.exp(-q * T) / (2 * sqrt_T)
                - r * K * math.exp(-r * T) * norm.cdf(d2)
                + q * S * math.exp(-q * T) * norm.cdf(d1)
            )
            rho = K * T * math.exp(-r * T) * norm.cdf(d2)
        else:
            delta = -math.exp(-q * T) * norm.cdf(-d1)
            theta = (
                -S * norm.pdf(d1) * sigma * math.exp(-q * T) / (2 * sqrt_T)
                + r * K * math.exp(-r * T) * norm.cdf(-d2)
                - q * S * math.exp(-q * T) * norm.cdf(-d1)
            )
            rho = -K * T * math.exp(-r * T) * norm.cdf(-d2)

        gamma = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * sqrt_T)
        vega = S * math.exp(-q * T) * norm.pdf(d1) * sqrt_T

        return {
            "delta": delta * self.notional,
            "gamma": gamma * self.notional,
            "vega": vega * self.notional / 100,  # per 1-vol-point
            "theta": theta * self.notional / 365,  # per day
            "rho": rho * self.notional / 10000,  # per 1bp
        }

    # ── primary interface ───────────────────────────────────────
    def price(self) -> PricingResult:
        errors = self.validate_inputs()
        if errors:
            raise ValueError(f"Input validation failed: {errors}")

        bs_price = self.price_black_scholes()
        binom_price = self.price_binomial()

        methods: dict[str, float] = {
            "black_scholes": bs_price,
            "binomial_tree": binom_price,
        }

        primary = bs_price if self.exercise_style == "european" else binom_price
        greeks = self.bs_greeks()

        return PricingResult(
            fair_value=primary,
            method="black_scholes" if self.exercise_style == "european" else "binomial_tree",
            currency=self.currency,
            greeks=greeks,
            diagnostics={
                "option_type": self.option_type,
                "exercise_style": self.exercise_style,
                "moneyness": round(self.spot / self.strike, 4),
            },
            methods=methods,
        )

    def calculate_greeks(self) -> dict[str, float]:
        return self.bs_greeks()
