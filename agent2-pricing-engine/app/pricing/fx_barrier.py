"""FX Barrier Option pricer (Double-No-Touch, Knock-In, Knock-Out).

Implements five pricing methods:
  1. Analytical — eigenfunction (Fourier) series for continuous double barrier
  2. Monte Carlo — path simulation with discrete barrier monitoring
  3. PDE Finite Difference — Crank-Nicolson on log-spot grid
  4. Local Vol Dupire — PDE with calibrated local-vol surface
  5. QuantLib — analytic double-barrier engine (if installed)
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import norm

from app.greeks.calculator import GreeksCalculator
from app.monte_carlo.engine import MCConfig, MonteCarloEngine
from app.pricing.base import BasePricer, PricingResult
from app.pricing.fx_pde import FXBarrierPDE, LocalVolDupirePricer


class FXBarrierPricer(BasePricer):
    """Price FX barrier options (DNT, KI, KO variants)."""

    def __init__(
        self,
        spot: float,
        lower_barrier: float,
        upper_barrier: float,
        maturity: float,
        notional: float,
        vol: float,
        r_dom: float,
        r_for: float,
        barrier_type: str = "DNT",
        currency: str = "USD",
        mc_paths: int = 50_000,
    ):
        self.spot = spot
        self.lower_barrier = lower_barrier
        self.upper_barrier = upper_barrier
        self.maturity = maturity
        self.notional = notional
        self.vol = vol
        self.r_dom = r_dom
        self.r_for = r_for
        self.barrier_type = barrier_type.upper()
        self.currency = currency
        self.mc_paths = mc_paths

    # ── validation ──────────────────────────────────────────────
    def validate_inputs(self) -> list[str]:
        errors: list[str] = []
        if self.lower_barrier >= self.upper_barrier:
            errors.append("lower_barrier must be < upper_barrier")
        if not (self.lower_barrier < self.spot < self.upper_barrier):
            errors.append("spot must be between the barriers")
        if self.maturity <= 0:
            errors.append("maturity must be > 0")
        if self.vol <= 0:
            errors.append("volatility must be > 0")
        return errors

    # ── Method 1: analytical (eigenfunction expansion) ──────────
    def _survival_probability_series(self, n_terms: int = 200) -> float:
        """
        Continuous double-barrier survival probability via the
        eigenfunction (Fourier-series) expansion for a killed diffusion.

        For log-price X(t) = x + mu*t + sigma*W(t) absorbed at 0 and w:

            P(survive) = exp(-alpha*x - mu^2*T/(2*sigma^2))
                         * (2/w) * SUM_n  sin(n*pi*x/w) * exp(-lambda_n*T) * J_n

        where alpha = mu/sigma^2, lambda_n = 0.5*(n*pi*sigma/w)^2,
        and J_n is the integral of exp(alpha*sigma^2*y)*sin(n*pi*y/w) over [0, w].
        """
        sigma = self.vol
        T = self.maturity
        mu = self.r_dom - self.r_for - 0.5 * sigma**2

        # barrier width and position in log space
        w = math.log(self.upper_barrier / self.lower_barrier)
        x = math.log(self.spot / self.lower_barrier)  # 0 < x < w

        a = mu / (sigma**2)  # drift parameter for Girsanov

        prefactor = math.exp(-a * x * sigma**2 / sigma**2 - mu**2 * T / (2 * sigma**2))
        # simplifies to exp(-mu*x/sigma^2 - mu^2*T/(2*sigma^2))
        prefactor = math.exp(-mu * x / sigma**2 - mu**2 * T / (2 * sigma**2))

        total = 0.0
        for n in range(1, n_terms + 1):
            b_n = n * math.pi / w

            # eigenvalue decay
            lambda_n_T = 0.5 * (b_n * sigma) ** 2 * T
            decay = math.exp(-lambda_n_T)
            if decay < 1e-15:
                break  # remaining terms negligible

            # J_n = integral_0^w exp(a_coeff * y) * sin(b_n * y) dy
            a_coeff = mu / sigma**2
            if abs(a_coeff) < 1e-14:
                # zero-drift case: integral = (w/(n*pi))*(1 - cos(n*pi))
                J_n = (1 - math.cos(n * math.pi)) / b_n
            else:
                # closed form: b_n * [1 - (-1)^n * exp(a_coeff*w)] / (a_coeff^2 + b_n^2)
                J_n = b_n * (1 - ((-1) ** n) * math.exp(a_coeff * w)) / (a_coeff**2 + b_n**2)

            total += math.sin(b_n * x) * decay * J_n

        prob = prefactor * (2.0 / w) * total
        return max(0.0, min(1.0, prob))

    def price_analytical(self) -> float:
        """Analytical DNT fair value via reflection-principle series."""
        sp = self._survival_probability_series()
        discount = math.exp(-self.r_dom * self.maturity)

        if self.barrier_type == "DNT":
            return self.notional * sp * discount
        elif self.barrier_type == "DOT":
            # Double-One-Touch: pays if *either* barrier is hit
            return self.notional * (1 - sp) * discount
        else:
            # For single-barrier KI/KO, still use survival prob
            return self.notional * sp * discount

    # ── Method 2: Monte Carlo ───────────────────────────────────
    def price_monte_carlo(self, mc_config: MCConfig | None = None) -> float:
        cfg = mc_config or MCConfig(num_paths=self.mc_paths)
        engine = MonteCarloEngine(cfg)

        drift = self.r_dom - self.r_for
        paths = engine.generate_paths(
            self.spot, drift, self.vol, self.maturity
        )

        # Check barriers on every time step
        breached = np.any(
            (paths <= self.lower_barrier) | (paths >= self.upper_barrier),
            axis=1,
        )
        survived = ~breached
        survival_rate = float(np.mean(survived))

        discount = math.exp(-self.r_dom * self.maturity)

        if self.barrier_type == "DNT":
            return self.notional * survival_rate * discount
        elif self.barrier_type == "DOT":
            return self.notional * (1 - survival_rate) * discount
        else:
            return self.notional * survival_rate * discount

    # ── Method 3: PDE Finite Difference (Crank-Nicolson) ────────
    def price_pde(self) -> float:
        pde = FXBarrierPDE(
            spot=self.spot,
            lower_barrier=self.lower_barrier,
            upper_barrier=self.upper_barrier,
            maturity=self.maturity,
            notional=self.notional,
            vol=self.vol,
            r_dom=self.r_dom,
            r_for=self.r_for,
            barrier_type=self.barrier_type,
        )
        return pde.price()

    # ── Method 4: Local Vol Dupire ─────────────────────────────
    def price_local_vol(
        self, vol_surface: list[dict[str, float]] | None = None
    ) -> float:
        lv = LocalVolDupirePricer(
            spot=self.spot,
            lower_barrier=self.lower_barrier,
            upper_barrier=self.upper_barrier,
            maturity=self.maturity,
            notional=self.notional,
            r_dom=self.r_dom,
            r_for=self.r_for,
            vol_surface=vol_surface,
            flat_vol=self.vol,
            barrier_type=self.barrier_type,
        )
        return lv.price()

    # ── Method 5: QuantLib (optional) ──────────────────────────
    def price_quantlib(self) -> float | None:
        """Price via QuantLib if installed."""
        try:
            import QuantLib as ql
        except ImportError:
            return None

        today = ql.Date.todaysDate()
        ql.Settings.instance().evaluationDate = today

        day_count = ql.Actual365Fixed()
        calendar = ql.TARGET()
        maturity_date = today + ql.Period(
            int(round(self.maturity * 365)), ql.Days
        )

        spot_handle = ql.QuoteHandle(ql.SimpleQuote(self.spot))
        r_dom_ts = ql.YieldTermStructureHandle(
            ql.FlatForward(today, self.r_dom, day_count)
        )
        r_for_ts = ql.YieldTermStructureHandle(
            ql.FlatForward(today, self.r_for, day_count)
        )
        vol_ts = ql.BlackVolTermStructureHandle(
            ql.BlackConstantVol(today, calendar, self.vol, day_count)
        )
        process = ql.BlackScholesMertonProcess(
            spot_handle, r_for_ts, r_dom_ts, vol_ts
        )

        payoff = ql.CashOrNothingPayoff(ql.Option.Call, self.spot, 1.0)
        exercise = ql.EuropeanExercise(maturity_date)

        barrier_option = ql.DoubleBarrierOption(
            ql.DoubleBarrier.KnockOut,
            self.lower_barrier,
            self.upper_barrier,
            0.0,  # rebate
            payoff,
            exercise,
        )
        engine = ql.AnalyticDoubleBarrierEngine(process)
        barrier_option.setPricingEngine(engine)

        return self.notional * barrier_option.NPV()

    # ── primary interface ───────────────────────────────────────
    def price(self) -> PricingResult:
        errors = self.validate_inputs()
        if errors:
            raise ValueError(f"Input validation failed: {errors}")

        analytical = self.price_analytical()
        mc = self.price_monte_carlo()
        pde = self.price_pde()
        local_vol = self.price_local_vol()
        ql_price = self.price_quantlib()

        methods: dict[str, float] = {
            "analytical": analytical,
            "monte_carlo": mc,
            "pde_finite_difference": pde,
            "local_vol_dupire": local_vol,
        }
        if ql_price is not None:
            methods["quantlib"] = ql_price

        sp = self._survival_probability_series()
        greeks = self.calculate_greeks()

        return PricingResult(
            fair_value=analytical,
            method="analytical",
            currency=self.currency,
            greeks=greeks,
            diagnostics={
                "survival_probability": round(sp, 6),
                "barrier_type": self.barrier_type,
            },
            methods=methods,
        )

    # ── Greeks ──────────────────────────────────────────────────
    def calculate_greeks(self) -> dict[str, float]:
        calc = GreeksCalculator(self, self.price_analytical)
        return calc.all(
            spot_attr="spot",
            vol_attr="vol",
            maturity_attr="maturity",
            rate_attr="r_dom",
        )
