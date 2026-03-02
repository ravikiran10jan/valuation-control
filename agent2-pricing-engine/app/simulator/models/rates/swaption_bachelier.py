"""Bachelier (Normal) model for European swaptions.

Prices payer and receiver swaptions assuming the swap rate follows
arithmetic Brownian motion (normal distribution).  This is the
market-standard model when rates can go negative and when vol is
quoted in basis-point (normal) terms.
"""

from __future__ import annotations

import math
from typing import Any

from scipy.stats import norm

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


@ModelRegistry.register
class SwaptionBachelierModel(BaseSimulatorModel):

    model_id = "swaption_bachelier"
    model_name = "Swaption — Bachelier (Normal Vol)"
    product_type = "European Swaption"
    asset_class = "rates"

    short_description = "Normal-vol swaption pricing — handles negative rates naturally"
    long_description = (
        "Prices European swaptions (options to enter into an interest rate swap) "
        "using the Bachelier (1900) / Normal model. The underlying swap rate is "
        "assumed to follow arithmetic Brownian motion: dF = σ_n dW, where σ_n is "
        "the normal (basis-point) volatility. Unlike Black-76 (log-normal), this "
        "model naturally handles zero and negative rates. It is the market standard "
        "for EUR and JPY swaptions and increasingly used for USD. A payer swaption "
        "gives the right to enter a payer swap (pay fixed, receive float). A receiver "
        "swaption gives the right to enter a receiver swap."
    )

    when_to_use = [
        "European swaptions (payer and receiver)",
        "When rates can be negative (EUR, JPY, CHF)",
        "When vol is quoted in basis-point (normal) terms",
        "As baseline model for swaption books",
        "When log-normal model gives implausible results near zero rates",
    ]
    when_not_to_use = [
        "Bermudan swaptions (need tree/MC with exercise strategy)",
        "When smile matters — use SABR or shifted log-normal",
        "CMS swaptions (need convexity adjustment)",
        "When vol is quoted in % (log-normal) terms — use Black-76",
    ]
    assumptions = [
        "Swap rate follows arithmetic Brownian motion: dF = σ_n dW",
        "Constant normal volatility (no smile, no term structure of vol)",
        "Deterministic discount factors (annuity is non-stochastic)",
        "European exercise only (single exercise date)",
        "No credit risk or margin considerations",
    ]
    limitations = [
        "No smile — same vol for all strikes",
        "Normal model allows negative rates (which may be unrealistic for some ccy)",
        "No exercise boundary for Bermudans",
        "Annuity assumed constant — ignores convexity (CMS adjustment needed)",
        "Single-factor: no decorrelation between rates at different tenors",
    ]

    formula_latex = (
        r"V_{payer} = A \cdot \left[(F - K) N(d) + \sigma_n \sqrt{T}\, n(d)\right]"
        r"\quad d = \frac{F - K}{\sigma_n \sqrt{T}}"
    )
    formula_plain = (
        "Payer = A × [(F-K)·N(d) + σ_n·√T·n(d)],  "
        "Receiver = A × [(K-F)·N(-d) + σ_n·√T·n(d)],  "
        "d = (F-K) / (σ_n·√T),  A = annuity of underlying swap"
    )

    # ── Parameters ──────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "notional", "Notional", "Swaption notional amount",
                "float", 10_000_000.0, 1.0, None, 100_000.0, unit="$",
            ),
            ParameterSpec(
                "forward_rate", "Forward Swap Rate (F)",
                "At-the-money forward swap rate",
                "float", 0.045, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "strike", "Strike (K)", "Swaption strike rate",
                "float", 0.045, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "option_expiry", "Option Expiry", "Time to swaption expiry in years",
                "float", 1.0, 0.01, 30.0, 0.25, unit="years",
            ),
            ParameterSpec(
                "swap_tenor", "Swap Tenor", "Tenor of the underlying swap in years",
                "float", 5.0, 0.25, 50.0, 0.25, unit="years",
            ),
            ParameterSpec(
                "normal_vol", "Normal Vol (σ_n)",
                "Annualized normal (basis-point) volatility in decimal. "
                "E.g. 0.0060 = 60 bps/yr.",
                "float", 0.0060, 0.0001, 0.1, 0.0001, unit="decimal",
            ),
            ParameterSpec(
                "swaption_type", "Type", "Payer or Receiver swaption",
                "select", "payer", options=["payer", "receiver"],
            ),
            ParameterSpec(
                "swap_freq", "Swap Frequency", "Payments per year on underlying swap",
                "int", 2, 1, 12, 1,
            ),
            ParameterSpec(
                "ois_rate", "OIS Rate", "Flat OIS rate for discounting",
                "float", 0.043, -0.05, 0.5, 0.001, unit="decimal",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "1Y×5Y ATM Payer": {
                "notional": 10_000_000.0,
                "forward_rate": 0.045, "strike": 0.045,
                "option_expiry": 1.0, "swap_tenor": 5.0,
                "normal_vol": 0.0060, "swaption_type": "payer",
                "swap_freq": 2, "ois_rate": 0.043,
            },
            "5Y×10Y OTM Receiver (K=3%)": {
                "notional": 50_000_000.0,
                "forward_rate": 0.045, "strike": 0.03,
                "option_expiry": 5.0, "swap_tenor": 10.0,
                "normal_vol": 0.0070, "swaption_type": "receiver",
                "swap_freq": 2, "ois_rate": 0.043,
            },
            "3M×2Y ATM Payer (short-dated)": {
                "notional": 25_000_000.0,
                "forward_rate": 0.048, "strike": 0.048,
                "option_expiry": 0.25, "swap_tenor": 2.0,
                "normal_vol": 0.0055, "swaption_type": "payer",
                "swap_freq": 4, "ois_rate": 0.045,
            },
            "2Y×30Y ATM Receiver (long swap)": {
                "notional": 100_000_000.0,
                "forward_rate": 0.044, "strike": 0.044,
                "option_expiry": 2.0, "swap_tenor": 30.0,
                "normal_vol": 0.0065, "swaption_type": "receiver",
                "swap_freq": 2, "ois_rate": 0.043,
            },
        }

    # ── Calculation ────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        N_notional = float(params["notional"])
        F = float(params["forward_rate"])
        K = float(params["strike"])
        T_opt = float(params["option_expiry"])
        T_swap = float(params["swap_tenor"])
        sigma_n = float(params["normal_vol"])
        is_payer = params.get("swaption_type", "payer").lower() == "payer"
        swap_freq = int(params.get("swap_freq", 2))
        r_ois = float(params.get("ois_rate", 0.043))

        steps: list[CalculationStep] = []
        sqrt_T = math.sqrt(T_opt)

        # Step 1: compute annuity of the underlying swap
        dt_swap = 1.0 / swap_freq
        n_swap_periods = int(round(T_swap * swap_freq))
        # Discount factors from swaption expiry onward
        annuity = 0.0
        for i in range(n_swap_periods):
            t_pay = T_opt + (i + 1) * dt_swap
            df = math.exp(-r_ois * t_pay)
            annuity += dt_swap * df

        steps.append(CalculationStep(
            step_number=1,
            label="Annuity of underlying swap",
            formula=r"A = \sum_{i=1}^{n} \tau_i \cdot DF(T_{opt} + i \cdot \tau)",
            substitution=(
                f"Swap: {n_swap_periods} periods × {dt_swap:.2f}Y, "
                f"starting at T_opt = {T_opt}Y.  "
                f"OIS rate = {r_ois*100:.2f}%.  Annuity = {annuity:.6f}"
            ),
            result=round(annuity, 6),
            explanation=(
                "The annuity (or PVBP) of the underlying swap. It converts the "
                "swaption payoff from rate terms to dollar terms."
            ),
        ))

        # Step 2: d statistic
        sigma_sqrt_T = sigma_n * sqrt_T
        if sigma_sqrt_T < 1e-12:
            # Near-zero vol or near-zero expiry: intrinsic
            if is_payer:
                price_unit = max(F - K, 0)
            else:
                price_unit = max(K - F, 0)
            d = 0.0
        else:
            d = (F - K) / sigma_sqrt_T
            if is_payer:
                price_unit = (F - K) * norm.cdf(d) + sigma_sqrt_T * norm.pdf(d)
            else:
                price_unit = (K - F) * norm.cdf(-d) + sigma_sqrt_T * norm.pdf(d)

        steps.append(CalculationStep(
            step_number=2,
            label="Bachelier d-statistic",
            formula=r"d = \frac{F - K}{\sigma_n \sqrt{T}}",
            substitution=(
                f"d = ({F} - {K}) / ({sigma_n} × √{T_opt})"
                f" = {F - K:.6f} / {sigma_sqrt_T:.6f}"
                f" = {d:.6f}"
            ),
            result=round(d, 6),
            explanation=(
                "d measures how far the forward rate is from the strike, "
                "in units of the normal volatility × √T."
            ),
        ))

        # Step 3: normal CDF and PDF
        Nd = norm.cdf(d)
        Nmd = norm.cdf(-d)
        nd = norm.pdf(d)

        steps.append(CalculationStep(
            step_number=3,
            label="Normal CDF/PDF values",
            formula=r"N(d),\; N(-d),\; n(d)",
            substitution=(
                f"N({d:.4f}) = {Nd:.6f},  N({-d:.4f}) = {Nmd:.6f},  "
                f"n({d:.4f}) = {nd:.6f}"
            ),
            result=round(Nd, 6),
            explanation="Standard normal distribution values for the pricing formula.",
        ))

        # Step 4: unit swaption price (per unit notional, before annuity)
        steps.append(CalculationStep(
            step_number=4,
            label=f"{'Payer' if is_payer else 'Receiver'} price (rate terms)",
            formula=(
                r"V_{payer}/A = (F-K)N(d) + \sigma_n\sqrt{T}\,n(d)"
                if is_payer else
                r"V_{rec}/A = (K-F)N(-d) + \sigma_n\sqrt{T}\,n(d)"
            ),
            substitution=(
                (f"({F}-{K})×{Nd:.6f} + {sigma_sqrt_T:.6f}×{nd:.6f}"
                 if is_payer else
                 f"({K}-{F})×{Nmd:.6f} + {sigma_sqrt_T:.6f}×{nd:.6f}")
                + f" = {price_unit:.8f}"
            ),
            result=round(price_unit, 8),
            explanation=(
                "Swaption value per unit notional in 'rate' terms, "
                "before multiplying by the annuity."
            ),
        ))

        # Step 5: dollar price
        price_annuity = price_unit * annuity
        price_dollar = price_annuity * N_notional

        steps.append(CalculationStep(
            step_number=5,
            label="Dollar price",
            formula=r"V = N \times A \times V_{unit}",
            substitution=(
                f"V = {N_notional:,.0f} × {annuity:.6f} × {price_unit:.8f}"
                f" = {price_dollar:,.2f}"
            ),
            result=round(price_dollar, 2),
            explanation="Total swaption premium in dollar terms.",
        ))

        # Step 6: Greeks
        # Delta: dV/dF = A × N(d) for payer, -A × N(-d) for receiver
        if is_payer:
            delta_unit = annuity * Nd
        else:
            delta_unit = -annuity * Nmd
        delta_dollar = delta_unit * N_notional

        # Gamma: d²V/dF² = A × n(d) / (σ√T)
        if sigma_sqrt_T > 1e-12:
            gamma_unit = annuity * nd / sigma_sqrt_T
        else:
            gamma_unit = 0.0
        gamma_dollar = gamma_unit * N_notional

        # Vega (normal): dV/dσ_n = A × √T × n(d)
        vega_unit = annuity * sqrt_T * nd
        vega_dollar = vega_unit * N_notional

        # Theta: approximate as -0.5 × σ_n² × Γ (for ATM)
        theta_unit = -0.5 * sigma_n**2 * gamma_unit if sigma_sqrt_T > 1e-12 else 0.0
        theta_dollar = theta_unit * N_notional

        steps.append(CalculationStep(
            step_number=6,
            label="Greeks",
            formula=(
                r"\Delta = A \cdot N(d),\;\;"
                r"\Gamma = \frac{A \cdot n(d)}{\sigma_n \sqrt{T}},\;\;"
                r"\mathcal{V}_n = A \cdot \sqrt{T} \cdot n(d)"
            ),
            substitution=(
                f"Delta = {delta_dollar:,.0f} (per 1 rate unit).  "
                f"Gamma = {gamma_dollar:,.0f} (per 1 rate unit²).  "
                f"Vega_n = {vega_dollar:,.0f} (per 1 unit σ_n).  "
                f"Vega_1bp = {vega_dollar * 0.0001:,.0f} (per 1bp σ_n)"
            ),
            result=round(delta_dollar, 0),
            explanation=(
                "Normal delta: dollar change per unit shift in the forward swap rate. "
                "Normal vega: dollar change per unit shift in normal vol. "
                "Vega_1bp is the sensitivity per 1bp vol change."
            ),
        ))

        # Step 7: put-call parity check
        # Payer - Receiver = A × (F - K) × N
        parity_value = annuity * (F - K) * N_notional
        if is_payer:
            implied_receiver = price_dollar - parity_value
        else:
            implied_payer = price_dollar + parity_value

        steps.append(CalculationStep(
            step_number=7,
            label="Put-call parity",
            formula=r"V_{payer} - V_{receiver} = N \cdot A \cdot (F - K)",
            substitution=(
                f"N×A×(F-K) = {N_notional:,.0f} × {annuity:.6f} × "
                f"({F}-{K}) = {parity_value:,.2f}.  "
                + (f"Implied receiver = {price_dollar:,.2f} - {parity_value:,.2f}"
                   f" = {price_dollar - parity_value:,.2f}"
                   if is_payer else
                   f"Implied payer = {price_dollar:,.2f} + {parity_value:,.2f}"
                   f" = {price_dollar + parity_value:,.2f}")
            ),
            result=round(parity_value, 2),
            explanation=(
                "Swaption put-call parity: the difference between payer and "
                "receiver equals the present value of a forward-starting swap."
            ),
        ))

        # Premium in bps of notional
        premium_bps = price_dollar / N_notional * 10000

        return SimulatorResult(
            fair_value=round(price_dollar, 2),
            method="Bachelier / Normal Model",
            greeks={
                "delta": round(delta_dollar, 2),
                "gamma": round(gamma_dollar, 2),
                "vega_normal": round(vega_dollar, 2),
                "vega_1bp": round(vega_dollar * 0.0001, 2),
                "theta_annual": round(theta_dollar, 2),
            },
            calculation_steps=steps,
            diagnostics={
                "d": round(d, 6),
                "N_d": round(Nd, 6),
                "n_d": round(nd, 6),
                "annuity": round(annuity, 6),
                "price_rate_terms": round(price_unit, 8),
                "price_annuity_terms": round(price_annuity, 8),
                "price_dollar": round(price_dollar, 2),
                "premium_bps": round(premium_bps, 2),
                "normal_vol_bps": round(sigma_n * 10000, 1),
                "moneyness_bps": round((F - K) * 10000, 1),
                "parity_swap_value": round(parity_value, 2),
                "forward_rate": F,
                "strike": K,
            },
        )
