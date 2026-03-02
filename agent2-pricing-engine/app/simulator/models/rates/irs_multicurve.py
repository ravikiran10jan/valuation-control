"""Interest Rate Swap (IRS) pricing with post-crisis multi-curve framework.

OIS discounting + IBOR forward rate projection — the standard since 2008.
Computes the fixed-rate par swap rate and mark-to-market of an existing swap.
"""

from __future__ import annotations

import math
from typing import Any

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


def _bootstrap_discount_factors(rates: list[float], tenors: list[float]) -> list[float]:
    """Bootstrap zero-coupon discount factors from par swap rates (simple)."""
    dfs = []
    for i, (r, t) in enumerate(zip(rates, tenors)):
        if i == 0:
            df = 1.0 / (1.0 + r * t)
        else:
            # par swap rate implies: sum(r * dt_j * df_j) + df_n = 1
            numerator = 1.0
            dt = tenors[0] if i == 0 else tenors[i] - tenors[i - 1]
            coupon_sum = sum(
                r * (tenors[j] - (tenors[j - 1] if j > 0 else 0.0)) * dfs[j]
                for j in range(i)
            )
            dt_i = tenors[i] - tenors[i - 1]
            df = (1.0 - coupon_sum) / (1.0 + r * dt_i)
        dfs.append(df)
    return dfs


def _interp_df(target_t: float, tenors: list[float], dfs: list[float]) -> float:
    """Log-linear interpolation of discount factors."""
    if target_t <= 0:
        return 1.0
    if target_t <= tenors[0]:
        log_df = math.log(dfs[0]) * target_t / tenors[0]
        return math.exp(log_df)
    if target_t >= tenors[-1]:
        log_df = math.log(dfs[-1]) * target_t / tenors[-1]
        return math.exp(log_df)
    for i in range(1, len(tenors)):
        if target_t <= tenors[i]:
            frac = (target_t - tenors[i - 1]) / (tenors[i] - tenors[i - 1])
            log_df = math.log(dfs[i - 1]) + frac * (math.log(dfs[i]) - math.log(dfs[i - 1]))
            return math.exp(log_df)
    return dfs[-1]


@ModelRegistry.register
class IRSMultiCurveModel(BaseSimulatorModel):

    model_id = "irs_multicurve"
    model_name = "IRS Multi-Curve DCF"
    product_type = "Interest Rate Swap"
    asset_class = "rates"

    short_description = "Post-crisis IRS pricing with OIS discounting and IBOR projection"
    long_description = (
        "Prices a plain vanilla interest rate swap using the post-2008 multi-curve "
        "framework. The floating leg projects forward IBOR rates from the IBOR curve "
        "(e.g. 3M SOFR, 3M EURIBOR), while all cash flows are discounted using the "
        "OIS curve (e.g. Fed Funds, ESTR). Before 2008, a single LIBOR curve was used "
        "for both projection and discounting. The spread between OIS and IBOR (the "
        "basis) reflects counterparty credit and liquidity risk. The model computes "
        "the par swap rate, MTM, DV01, and convexity for receiver and payer swaps."
    )

    when_to_use = [
        "Pricing and risk-managing vanilla IRS (fixed vs float)",
        "Computing par swap rates for any tenor",
        "DV01 and curve sensitivity analysis",
        "When OIS-IBOR basis matters (post-crisis standard)",
        "Benchmarking more complex rates derivatives",
    ]
    when_not_to_use = [
        "Cross-currency swaps (need FX component and xccy basis)",
        "Basis swaps (3M vs 6M) — need tenor basis modeling",
        "When convexity adjustment is needed (CMS, in-arrears)",
        "For options on swaps — use swaption models",
    ]
    assumptions = [
        "Piecewise flat/linear forward rates between curve nodes",
        "OIS curve for discounting, IBOR curve for forward projection",
        "No counterparty credit risk (clean price, no CVA/DVA)",
        "Act/360 or 30/360 day count (simplified)",
        "Periodic compounding matching payment frequency",
    ]
    limitations = [
        "Simplified curve bootstrap — production uses cubic spline",
        "Does not handle stubs, broken periods, or payment delays",
        "No convexity adjustment for timing mismatches",
        "Ignores settlement lag and business day conventions",
    ]

    formula_latex = (
        r"\text{Par Rate} = \frac{1 - DF_N}{\sum_{i=1}^{N} \tau_i \cdot DF_i^{OIS}}"
        r"\quad\quad"
        r"\text{MTM} = N \left[\sum_{i} \tau_i f_i^{IBOR} DF_i^{OIS}"
        r" - R_{fix} \sum_{i} \tau_i DF_i^{OIS}\right]"
    )
    formula_plain = (
        "Par Rate = (1 - DF_N) / sum(τ_i × DF_i),  "
        "MTM = Notional × [Float PV - Fixed PV],  "
        "where f_i = (DF_{i-1}/DF_i - 1)/τ_i is the forward rate"
    )

    # ── Parameters ──────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "notional", "Notional", "Swap notional amount",
                "float", 10_000_000.0, 1.0, None, 100_000.0, unit="$",
            ),
            ParameterSpec(
                "fixed_rate", "Fixed Rate", "Fixed coupon rate (decimal). Set 0 for par.",
                "float", 0.0, -0.1, 0.5, 0.0001, unit="decimal",
            ),
            ParameterSpec(
                "maturity", "Swap Tenor", "Maturity in years",
                "float", 5.0, 0.25, 50.0, 0.25, unit="years",
            ),
            ParameterSpec(
                "pay_freq", "Payment Frequency", "Payments per year",
                "int", 4, 1, 12, 1,
            ),
            ParameterSpec(
                "direction", "Direction", "Payer (pay fixed) or Receiver (receive fixed)",
                "select", "payer", options=["payer", "receiver"],
            ),
            ParameterSpec(
                "ois_rate_1y", "OIS 1Y", "1-year OIS rate",
                "float", 0.048, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "ois_rate_2y", "OIS 2Y", "2-year OIS rate",
                "float", 0.045, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "ois_rate_5y", "OIS 5Y", "5-year OIS rate",
                "float", 0.042, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "ois_rate_10y", "OIS 10Y", "10-year OIS rate",
                "float", 0.043, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "ibor_spread", "IBOR-OIS Spread", "Spread of IBOR over OIS (basis points / 10000)",
                "float", 0.001, 0.0, 0.05, 0.0001, unit="decimal",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "5Y Payer Swap (at par)": {
                "notional": 10_000_000.0, "fixed_rate": 0.0,
                "maturity": 5.0, "pay_freq": 4, "direction": "payer",
                "ois_rate_1y": 0.048, "ois_rate_2y": 0.045,
                "ois_rate_5y": 0.042, "ois_rate_10y": 0.043,
                "ibor_spread": 0.001,
            },
            "10Y Receiver Swap (4.5% fixed)": {
                "notional": 50_000_000.0, "fixed_rate": 0.045,
                "maturity": 10.0, "pay_freq": 2, "direction": "receiver",
                "ois_rate_1y": 0.048, "ois_rate_2y": 0.045,
                "ois_rate_5y": 0.042, "ois_rate_10y": 0.043,
                "ibor_spread": 0.001,
            },
            "2Y Payer Swap (5% fixed)": {
                "notional": 25_000_000.0, "fixed_rate": 0.05,
                "maturity": 2.0, "pay_freq": 4, "direction": "payer",
                "ois_rate_1y": 0.048, "ois_rate_2y": 0.045,
                "ois_rate_5y": 0.042, "ois_rate_10y": 0.043,
                "ibor_spread": 0.0015,
            },
            "30Y Receiver Swap (at par)": {
                "notional": 100_000_000.0, "fixed_rate": 0.0,
                "maturity": 30.0, "pay_freq": 2, "direction": "receiver",
                "ois_rate_1y": 0.048, "ois_rate_2y": 0.045,
                "ois_rate_5y": 0.042, "ois_rate_10y": 0.043,
                "ibor_spread": 0.002,
            },
        }

    # ── Calculation ────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        N = float(params["notional"])
        fixed_rate = float(params["fixed_rate"])
        T = float(params["maturity"])
        freq = int(params.get("pay_freq", 4))
        direction = params.get("direction", "payer").lower()
        ibor_spread = float(params.get("ibor_spread", 0.001))

        ois_1y = float(params["ois_rate_1y"])
        ois_2y = float(params["ois_rate_2y"])
        ois_5y = float(params["ois_rate_5y"])
        ois_10y = float(params["ois_rate_10y"])

        steps: list[CalculationStep] = []

        # Step 1: build OIS discount curve
        ois_tenors = [1.0, 2.0, 5.0, 10.0]
        ois_rates = [ois_1y, ois_2y, ois_5y, ois_10y]
        ois_dfs = _bootstrap_discount_factors(ois_rates, ois_tenors)

        steps.append(CalculationStep(
            step_number=1,
            label="Bootstrap OIS discount curve",
            formula=r"DF_i = \frac{1 - \sum_{j<i} r \cdot \tau_j \cdot DF_j}{1 + r \cdot \tau_i}",
            substitution=(
                f"OIS rates: 1Y={ois_1y*100:.2f}%, 2Y={ois_2y*100:.2f}%, "
                f"5Y={ois_5y*100:.2f}%, 10Y={ois_10y*100:.2f}%.  "
                f"DFs: " + ", ".join(f"{t}Y={df:.6f}" for t, df in zip(ois_tenors, ois_dfs))
            ),
            result=round(ois_dfs[-1], 6),
            explanation=(
                "OIS discount factors bootstrapped from par OIS rates. "
                "These are used for discounting all swap cash flows."
            ),
        ))

        # Step 2: build payment schedule
        dt = 1.0 / freq
        n_periods = int(round(T * freq))
        schedule = [(i + 1) * dt for i in range(n_periods)]

        # Interpolate OIS DFs at each payment date
        df_ois = [_interp_df(t, ois_tenors, ois_dfs) for t in schedule]

        steps.append(CalculationStep(
            step_number=2,
            label="Payment schedule",
            formula=r"t_i = i / \text{freq},\quad i = 1, \ldots, T \times \text{freq}",
            substitution=(
                f"{n_periods} periods, dt = {dt:.4f}Y ({dt * 365:.0f} days).  "
                f"First 4 DFs: " + ", ".join(
                    f"DF({schedule[i]:.2f}Y)={df_ois[i]:.6f}"
                    for i in range(min(4, n_periods))
                )
            ),
            result=n_periods,
            explanation="Equally-spaced payment dates with interpolated OIS discount factors.",
        ))

        # Step 3: compute forward IBOR rates
        ibor_dfs = [_interp_df(t, ois_tenors, ois_dfs) / (1 + ibor_spread * t) for t in schedule]
        # Actually: forward IBOR = forward OIS + spread
        fwd_rates = []
        for i in range(n_periods):
            t_start = schedule[i] - dt
            t_end = schedule[i]
            df_start = _interp_df(t_start, ois_tenors, ois_dfs)
            df_end = _interp_df(t_end, ois_tenors, ois_dfs)
            fwd_ois = (df_start / df_end - 1.0) / dt
            fwd_ibor = fwd_ois + ibor_spread
            fwd_rates.append(fwd_ibor)

        steps.append(CalculationStep(
            step_number=3,
            label="Forward IBOR rates",
            formula=(
                r"f_i^{IBOR} = \frac{DF^{OIS}_{i-1} / DF^{OIS}_i - 1}{\tau_i}"
                r" + \text{spread}"
            ),
            substitution=(
                f"IBOR-OIS spread = {ibor_spread * 10000:.1f} bps.  "
                f"First 4 forwards: " + ", ".join(
                    f"f({schedule[i]:.2f}Y)={fwd_rates[i]*100:.3f}%"
                    for i in range(min(4, n_periods))
                )
            ),
            result=round(fwd_rates[0] * 100, 3),
            explanation=(
                "Forward IBOR rates = forward OIS rates + basis spread. "
                "These are used to project the floating leg cash flows."
            ),
        ))

        # Step 4: floating leg PV
        float_pv = 0.0
        for i in range(n_periods):
            float_pv += dt * fwd_rates[i] * df_ois[i]

        steps.append(CalculationStep(
            step_number=4,
            label="Floating leg PV (per unit notional)",
            formula=r"PV_{float} = \sum_{i=1}^{N} \tau_i \cdot f_i^{IBOR} \cdot DF_i^{OIS}",
            substitution=f"PV_float = {float_pv:.8f} (per unit notional)",
            result=round(float_pv, 8),
            explanation="Sum of discounted projected floating cash flows.",
        ))

        # Step 5: annuity (fixed leg DV01 factor)
        annuity = sum(dt * df for df in df_ois)

        steps.append(CalculationStep(
            step_number=5,
            label="Annuity factor",
            formula=r"A = \sum_{i=1}^{N} \tau_i \cdot DF_i^{OIS}",
            substitution=f"A = {annuity:.8f}",
            result=round(annuity, 8),
            explanation=(
                "The annuity (or PV01 per bp) represents the present value of "
                "receiving 1 unit per period, discounted at OIS."
            ),
        ))

        # Step 6: par swap rate
        par_rate = float_pv / annuity

        steps.append(CalculationStep(
            step_number=6,
            label="Par swap rate",
            formula=r"R_{par} = \frac{PV_{float}}{A}",
            substitution=(
                f"R_par = {float_pv:.8f} / {annuity:.8f} = {par_rate:.6f} "
                f"({par_rate * 100:.4f}%)"
            ),
            result=round(par_rate, 6),
            explanation=(
                "The fixed rate that makes the swap have zero MTM at inception. "
                "This is the fair mid-market swap rate."
            ),
        ))

        # If fixed_rate is 0, use par rate
        use_rate = par_rate if fixed_rate == 0.0 else fixed_rate
        fixed_pv = use_rate * annuity

        # Step 7: MTM
        if direction == "payer":
            mtm = N * (float_pv - fixed_pv)
        else:
            mtm = N * (fixed_pv - float_pv)

        steps.append(CalculationStep(
            step_number=7,
            label="Mark-to-Market",
            formula=(
                r"\text{MTM}_{payer} = N \times (PV_{float} - R_{fix} \times A)"
            ),
            substitution=(
                f"Fixed rate used = {use_rate * 100:.4f}%.  "
                f"Fixed PV = {fixed_pv:.8f}.  Float PV = {float_pv:.8f}.  "
                f"MTM ({direction}) = {N:,.0f} × "
                f"{'(' + f'{float_pv:.6f} - {fixed_pv:.6f}' + ')' if direction == 'payer' else '(' + f'{fixed_pv:.6f} - {float_pv:.6f}' + ')'}"
                f" = {mtm:,.2f}"
            ),
            result=round(mtm, 2),
            explanation=(
                "Positive MTM means the swap is in-the-money. For a payer swap, "
                "positive means float > fixed (rates rose). For a par swap, MTM = 0."
            ),
        ))

        # Step 8: DV01 and convexity
        bump = 0.0001  # 1bp
        # Bump all OIS rates up
        ois_rates_up = [r + bump for r in ois_rates]
        ois_dfs_up = _bootstrap_discount_factors(ois_rates_up, ois_tenors)
        df_ois_up = [_interp_df(t, ois_tenors, ois_dfs_up) for t in schedule]
        fwd_up = []
        for i in range(n_periods):
            t_start = schedule[i] - dt
            df_s = _interp_df(t_start, ois_tenors, ois_dfs_up)
            df_e = _interp_df(schedule[i], ois_tenors, ois_dfs_up)
            fwd_up.append((df_s / df_e - 1.0) / dt + ibor_spread)
        float_pv_up = sum(dt * f * d for f, d in zip(fwd_up, df_ois_up))
        ann_up = sum(dt * d for d in df_ois_up)
        if direction == "payer":
            mtm_up = N * (float_pv_up - use_rate * ann_up)
        else:
            mtm_up = N * (use_rate * ann_up - float_pv_up)

        # Bump down
        ois_rates_dn = [r - bump for r in ois_rates]
        ois_dfs_dn = _bootstrap_discount_factors(ois_rates_dn, ois_tenors)
        df_ois_dn = [_interp_df(t, ois_tenors, ois_dfs_dn) for t in schedule]
        fwd_dn = []
        for i in range(n_periods):
            t_start = schedule[i] - dt
            df_s = _interp_df(t_start, ois_tenors, ois_dfs_dn)
            df_e = _interp_df(schedule[i], ois_tenors, ois_dfs_dn)
            fwd_dn.append((df_s / df_e - 1.0) / dt + ibor_spread)
        float_pv_dn = sum(dt * f * d for f, d in zip(fwd_dn, df_ois_dn))
        ann_dn = sum(dt * d for d in df_ois_dn)
        if direction == "payer":
            mtm_dn = N * (float_pv_dn - use_rate * ann_dn)
        else:
            mtm_dn = N * (use_rate * ann_dn - float_pv_dn)

        dv01 = (mtm_up - mtm_dn) / 2.0
        convexity = (mtm_up - 2 * mtm + mtm_dn) / bump**2 / N

        steps.append(CalculationStep(
            step_number=8,
            label="DV01 and Convexity",
            formula=r"DV01 = \frac{V(r+1bp) - V(r-1bp)}{2}",
            substitution=(
                f"DV01 = ({mtm_up:,.2f} - {mtm_dn:,.2f}) / 2 = {dv01:,.2f}.  "
                f"Convexity = {convexity:,.2f}"
            ),
            result=round(dv01, 2),
            explanation=(
                "DV01 is the dollar change in MTM for a 1bp parallel shift in rates. "
                "Convexity measures the second-order sensitivity."
            ),
        ))

        return SimulatorResult(
            fair_value=round(mtm, 2),
            method="Multi-Curve DCF (OIS discounting)",
            greeks={
                "dv01": round(dv01, 2),
                "convexity": round(convexity, 2),
                "par_rate": round(par_rate, 6),
            },
            calculation_steps=steps,
            diagnostics={
                "par_rate": round(par_rate, 6),
                "par_rate_pct": round(par_rate * 100, 4),
                "fixed_rate_used": round(use_rate, 6),
                "annuity": round(annuity, 8),
                "float_pv_per_unit": round(float_pv, 8),
                "fixed_pv_per_unit": round(fixed_pv, 8),
                "mtm": round(mtm, 2),
                "dv01": round(dv01, 2),
                "convexity": round(convexity, 2),
                "n_periods": n_periods,
                "direction": direction,
                "ibor_spread_bps": round(ibor_spread * 10000, 1),
            },
        )
