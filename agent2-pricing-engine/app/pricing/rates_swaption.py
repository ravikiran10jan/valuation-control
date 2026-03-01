"""Hull-White 1-Factor Bermudan Swaption pricer.

Uses trinomial tree backward-induction for Bermudan exercise.
Optionally delegates to QuantLib for cross-validation.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar

from app.greeks.calculator import GreeksCalculator
from app.pricing.base import BasePricer, PricingResult


class HullWhitePricer(BasePricer):
    """Price Bermudan swaptions under the Hull-White 1-factor model."""

    def __init__(
        self,
        notional: float,
        fixed_rate: float,
        exercise_dates_years: list[float],
        swap_tenor: float,
        yield_curve: list[tuple[float, float]],
        kappa: float,
        sigma: float,
        pay_frequency: float = 0.5,
        currency: str = "USD",
    ):
        """
        Args:
            notional:  face notional.
            fixed_rate: strike coupon.
            exercise_dates_years: e.g. [1.0, 2.0, … 10.0] in year fractions.
            swap_tenor: tenor of the underlying swap (years).
            yield_curve: list of (tenor, zero_rate) pairs.
            kappa: mean-reversion speed.
            sigma: short-rate volatility.
            pay_frequency: payment frequency in years (0.5 = semi-annual).
        """
        self.notional = notional
        self.fixed_rate = fixed_rate
        self.exercise_dates = sorted(exercise_dates_years)
        self.swap_tenor = swap_tenor
        self.yield_curve = sorted(yield_curve, key=lambda x: x[0])
        self.kappa = kappa
        self.sigma = sigma
        self.pay_frequency = pay_frequency
        self.currency = currency

        # Derived
        self.vol = sigma  # alias for greeks calc

    # ── helpers ──────────────────────────────────────────────────
    def _zero_rate(self, t: float) -> float:
        """Linear interpolation on the zero-rate curve."""
        if t <= 0:
            return self.yield_curve[0][1]
        tenors = [p[0] for p in self.yield_curve]
        rates = [p[1] for p in self.yield_curve]
        return float(np.interp(t, tenors, rates))

    def _discount(self, t: float) -> float:
        return math.exp(-self._zero_rate(t) * t)

    def _annuity(self, start: float, tenor: float) -> float:
        """PV01 of a par swap starting at *start*, length *tenor*."""
        n_periods = int(round(tenor / self.pay_frequency))
        total = 0.0
        for i in range(1, n_periods + 1):
            t = start + i * self.pay_frequency
            total += self.pay_frequency * self._discount(t)
        return total

    def _swap_value(self, exercise_time: float, short_rate_shift: float = 0.0) -> float:
        """Intrinsic value of the underlying swap if exercised at *exercise_time*."""
        r_shift = short_rate_shift
        n_periods = int(round(self.swap_tenor / self.pay_frequency))
        pv_fixed = 0.0
        pv_float = 0.0

        for i in range(1, n_periods + 1):
            t = exercise_time + i * self.pay_frequency
            r = self._zero_rate(t) + r_shift
            df = math.exp(-r * t)
            pv_fixed += self.fixed_rate * self.pay_frequency * df
            # float leg approximation
            if i == 1:
                prev_df = math.exp(-(self._zero_rate(exercise_time) + r_shift) * exercise_time)
            else:
                t_prev = exercise_time + (i - 1) * self.pay_frequency
                prev_df = math.exp(-(self._zero_rate(t_prev) + r_shift) * t_prev)
            pv_float += prev_df - df

        return self.notional * (pv_float - pv_fixed)

    # ── trinomial-tree pricer ───────────────────────────────────
    def _price_tree(self, n_steps: int = 200) -> float:
        """
        Hull-White trinomial tree with Bermudan exercise.
        Simplified implementation: builds a recombining tree and
        does backward induction, checking exercise at each exercise date.
        """
        T_max = self.exercise_dates[-1] + self.swap_tenor
        dt = T_max / n_steps

        # Hull-White tree parameters
        dr = self.sigma * math.sqrt(3 * dt)
        j_max = int(math.ceil(0.1835 / (self.kappa * dt)))
        j_max = max(j_max, 3)

        # Build tree node values (short-rate deviations)
        n_nodes = 2 * j_max + 1

        # Transition probabilities for node j
        def probs(j: int) -> tuple[float, float, float]:
            eta = self.kappa * j * dt
            p_up = 1 / 6 + (eta**2 - eta) / 2 if abs(j) <= j_max else 0
            p_mid = 2 / 3 - eta**2 if abs(j) <= j_max else 1
            p_dn = 1 / 6 + (eta**2 + eta) / 2 if abs(j) <= j_max else 0
            # clamp
            p_up = max(0, min(1, p_up))
            p_mid = max(0, min(1, p_mid))
            p_dn = max(0, min(1, p_dn))
            total = p_up + p_mid + p_dn
            if total > 0:
                p_up /= total
                p_mid /= total
                p_dn /= total
            return p_up, p_mid, p_dn

        # Terminal payoff
        values = np.zeros(n_nodes)

        # Find exercise step indices
        exercise_steps = set()
        for ex_t in self.exercise_dates:
            step = int(round(ex_t / dt))
            if 0 < step < n_steps:
                exercise_steps.add(step)

        # Backward induction
        for step in range(n_steps - 1, -1, -1):
            t = step * dt
            new_values = np.zeros(n_nodes)

            for j_idx in range(n_nodes):
                j = j_idx - j_max
                r_node = self._zero_rate(t) + j * dr
                df_dt = math.exp(-max(r_node, 0.0001) * dt)

                p_up, p_mid, p_dn = probs(j)

                # successor indices (clamped to grid)
                j_up = min(j_idx + 1, n_nodes - 1)
                j_mid = j_idx
                j_dn = max(j_idx - 1, 0)

                continuation = df_dt * (
                    p_up * values[j_up]
                    + p_mid * values[j_mid]
                    + p_dn * values[j_dn]
                )

                if step in exercise_steps:
                    exercise_val = self._swap_value(t, j * dr)
                    new_values[j_idx] = max(continuation, exercise_val)
                else:
                    new_values[j_idx] = continuation

            values = new_values

        return float(values[j_max])  # root node

    # ── calibration ─────────────────────────────────────────────
    def calibrate_kappa(
        self,
        swaption_market_prices: dict[float, float],
    ) -> float:
        """Grid-search kappa that minimises squared pricing error."""

        def objective(kappa: float) -> float:
            self.kappa = kappa
            total_err = 0.0
            for ex_t, market_px in swaption_market_prices.items():
                model_px = self._swap_value(ex_t)
                total_err += (model_px - market_px) ** 2
            return total_err

        result = minimize_scalar(objective, bounds=(0.001, 0.10), method="bounded")
        best_kappa = result.x
        self.kappa = best_kappa
        return best_kappa

    # ── primary interface ───────────────────────────────────────
    def price(self) -> PricingResult:
        tree_value = self._price_tree()

        # QuantLib cross-check
        ql_value = self._price_quantlib()

        methods: dict[str, float] = {"trinomial_tree": tree_value}
        if ql_value is not None:
            methods["quantlib"] = ql_value

        greeks = self.calculate_greeks()

        return PricingResult(
            fair_value=tree_value,
            method="hull_white_trinomial_tree",
            currency=self.currency,
            greeks=greeks,
            diagnostics={
                "kappa": self.kappa,
                "sigma": self.sigma,
                "n_exercise_dates": len(self.exercise_dates),
            },
            methods=methods,
        )

    def _price_quantlib(self) -> float | None:
        try:
            import QuantLib as ql
        except ImportError:
            return None

        today = ql.Date.todaysDate()
        ql.Settings.instance().evaluationDate = today
        day_count = ql.Actual365Fixed()
        calendar = ql.TARGET()

        # Build yield curve
        dates = [today]
        rates = [self.yield_curve[0][1]]
        for tenor, rate in self.yield_curve:
            dates.append(today + ql.Period(int(round(tenor * 365)), ql.Days))
            rates.append(rate)
        curve = ql.ZeroCurve(dates, rates, day_count, calendar)
        curve_handle = ql.YieldTermStructureHandle(curve)

        # Hull-White model
        model = ql.HullWhite(curve_handle, self.kappa, self.sigma)

        # Build the Bermudan swaption
        fixed_schedule_dates = []
        float_schedule_dates = []
        start_date = today + ql.Period(
            int(round(self.exercise_dates[0] * 365)), ql.Days
        )
        end_date = start_date + ql.Period(
            int(round(self.swap_tenor * 12)), ql.Months
        )

        fixed_schedule = ql.Schedule(
            start_date, end_date,
            ql.Period(int(round(12 * self.pay_frequency)), ql.Months),
            calendar, ql.ModifiedFollowing, ql.ModifiedFollowing,
            ql.DateGeneration.Forward, False,
        )
        float_schedule = ql.Schedule(
            start_date, end_date,
            ql.Period(3, ql.Months),
            calendar, ql.ModifiedFollowing, ql.ModifiedFollowing,
            ql.DateGeneration.Forward, False,
        )

        index = ql.Euribor3M(curve_handle)

        swap = ql.VanillaSwap(
            ql.VanillaSwap.Payer,
            self.notional,
            fixed_schedule,
            self.fixed_rate,
            day_count,
            float_schedule,
            index,
            0.0,
            index.dayCounter(),
        )
        swap.setPricingEngine(ql.DiscountingSwapEngine(curve_handle))

        exercise_ql_dates = [
            today + ql.Period(int(round(t * 365)), ql.Days)
            for t in self.exercise_dates
        ]
        exercise = ql.BermudanExercise(exercise_ql_dates)
        swaption = ql.Swaption(swap, exercise)

        engine = ql.TreeSwaptionEngine(model, 200)
        swaption.setPricingEngine(engine)

        return swaption.NPV()

    # ── Greeks ──────────────────────────────────────────────────
    def calculate_greeks(self) -> dict[str, float]:
        calc = GreeksCalculator(self, self._price_tree)
        # Rate sensitivity: bump the entire curve via sigma proxy
        base = self._price_tree()

        # DV01: bump all zero rates by 1bp
        orig_curve = list(self.yield_curve)
        self.yield_curve = [(t, r + 0.0001) for t, r in orig_curve]
        up_val = self._price_tree()
        self.yield_curve = orig_curve

        # Vega: bump sigma
        orig_sigma = self.sigma
        self.sigma = orig_sigma + 0.01
        self.vol = self.sigma
        vega_val = self._price_tree() - base
        self.sigma = orig_sigma
        self.vol = self.sigma

        return {
            "dv01": up_val - base,
            "vega": vega_val,
        }
