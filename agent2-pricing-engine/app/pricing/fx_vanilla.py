"""FX Vanilla option pricer — Garman-Kohlhagen model.

Extension of Black-Scholes to FX, treating the foreign interest rate
as a continuous dividend yield:

    C = S*e^{-r_f*T} * N(d1) - K*e^{-r_d*T} * N(d2)
    P = K*e^{-r_d*T} * N(-d2) - S*e^{-r_f*T} * N(-d1)

where d1 = [ln(S/K) + (r_d - r_f + sigma^2/2)*T] / (sigma*sqrt(T))
      d2 = d1 - sigma*sqrt(T)
"""

from __future__ import annotations

import math
from typing import Any

from scipy.stats import norm

from app.greeks.calculator import GreeksCalculator
from app.pricing.base import BasePricer, PricingResult


class FXVanillaOptionPricer(BasePricer):
    """Garman-Kohlhagen FX vanilla option pricer."""

    def __init__(
        self,
        spot: float,
        strike: float,
        maturity: float,
        vol: float,
        r_dom: float,
        r_for: float,
        notional: float = 1_000_000,
        option_type: str = "call",
        currency_pair: str = "EURUSD",
        currency: str = "USD",
    ):
        self.spot = spot
        self.strike = strike
        self.maturity = maturity
        self.vol = vol
        self.r_dom = r_dom
        self.r_for = r_for
        self.notional = notional
        self.option_type = option_type.lower()
        self.currency_pair = currency_pair.upper().replace("/", "")
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

    # ── Garman-Kohlhagen ────────────────────────────────────────
    def _d1_d2(self) -> tuple[float, float]:
        S, K, T, sigma = self.spot, self.strike, self.maturity, self.vol
        r_d, r_f = self.r_dom, self.r_for
        d1 = (math.log(S / K) + (r_d - r_f + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        return d1, d2

    def price_garman_kohlhagen(self) -> float:
        S, K, T = self.spot, self.strike, self.maturity
        r_d, r_f = self.r_dom, self.r_for
        d1, d2 = self._d1_d2()

        if self.option_type == "call":
            px = S * math.exp(-r_f * T) * norm.cdf(d1) - K * math.exp(-r_d * T) * norm.cdf(d2)
        else:
            px = K * math.exp(-r_d * T) * norm.cdf(-d2) - S * math.exp(-r_f * T) * norm.cdf(-d1)

        return px * self.notional

    # ── analytical Greeks (GK-specific) ─────────────────────────
    def gk_greeks(self) -> dict[str, float]:
        S, K, T, sigma = self.spot, self.strike, self.maturity, self.vol
        r_d, r_f = self.r_dom, self.r_for
        d1, d2 = self._d1_d2()
        sqrt_T = math.sqrt(T)

        # Delta
        if self.option_type == "call":
            delta = math.exp(-r_f * T) * norm.cdf(d1)
        else:
            delta = -math.exp(-r_f * T) * norm.cdf(-d1)

        # Gamma
        gamma = math.exp(-r_f * T) * norm.pdf(d1) / (S * sigma * sqrt_T)

        # Vega
        vega = S * math.exp(-r_f * T) * norm.pdf(d1) * sqrt_T

        # Theta
        term1 = -S * norm.pdf(d1) * sigma * math.exp(-r_f * T) / (2 * sqrt_T)
        if self.option_type == "call":
            theta = term1 - r_d * K * math.exp(-r_d * T) * norm.cdf(d2) + r_f * S * math.exp(-r_f * T) * norm.cdf(d1)
        else:
            theta = term1 + r_d * K * math.exp(-r_d * T) * norm.cdf(-d2) - r_f * S * math.exp(-r_f * T) * norm.cdf(-d1)

        # Rho domestic
        if self.option_type == "call":
            rho_dom = K * T * math.exp(-r_d * T) * norm.cdf(d2)
        else:
            rho_dom = -K * T * math.exp(-r_d * T) * norm.cdf(-d2)

        # Rho foreign (phi)
        if self.option_type == "call":
            rho_for = -S * T * math.exp(-r_f * T) * norm.cdf(d1)
        else:
            rho_for = S * T * math.exp(-r_f * T) * norm.cdf(-d1)

        # Vanna: d(delta)/d(sigma) = d(vega)/d(S)
        vanna = -math.exp(-r_f * T) * norm.pdf(d1) * d2 / sigma

        # Volga: d(vega)/d(sigma)
        volga = vega * d1 * d2 / sigma

        return {
            "delta": delta * self.notional,
            "gamma": gamma * self.notional,
            "vega": vega * self.notional / 100,  # per 1 vol point
            "theta": theta * self.notional / 365,  # per day
            "rho_domestic": rho_dom * self.notional / 10_000,  # per 1bp
            "rho_foreign": rho_for * self.notional / 10_000,
            "vanna": vanna * self.notional,
            "volga": volga * self.notional / 100,
        }

    # ── BasePricer interface ────────────────────────────────────
    def price(self) -> PricingResult:
        errors = self.validate_inputs()
        if errors:
            raise ValueError(f"Input validation failed: {errors}")

        gk_price = self.price_garman_kohlhagen()
        greeks = self.gk_greeks()

        forward = self.spot * math.exp((self.r_dom - self.r_for) * self.maturity)

        return PricingResult(
            fair_value=gk_price,
            method="garman_kohlhagen",
            currency=self.currency,
            greeks=greeks,
            diagnostics={
                "currency_pair": self.currency_pair,
                "option_type": self.option_type,
                "moneyness": round(self.spot / self.strike, 4),
                "forward": round(forward, 6),
                "implied_vol": self.vol,
            },
            methods={"garman_kohlhagen": gk_price},
        )

    def calculate_greeks(self) -> dict[str, float]:
        return self.gk_greeks()
