"""Black-76 model for options on commodity futures.

Black (1976) is the standard analytical model for European options on futures.
It is identical to Black-Scholes but replaces the spot price with the futures price
F, and removes the dividend yield. The discount factor applies only to the premium,
not to the underlying, because futures require no upfront investment.
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


def _norm_cdf(x: float) -> float:
    """Standard normal CDF using math.erfc for zero-dependency."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


@ModelRegistry.register
class Black76CommodityModel(BaseSimulatorModel):

    model_id = "black76_commodity"
    model_name = "Black-76 Commodity Option"
    product_type = "Option on Commodity Future"
    asset_class = "commodity"

    short_description = (
        "Analytical Black-76 pricing for European options on commodity futures"
    )
    long_description = (
        "The Black (1976) model prices European options on futures contracts. "
        "Unlike Black-Scholes, Black-76 treats the futures price F as the underlying "
        "directly: the futures holder pays nothing upfront, so there is no cost-of-carry "
        "term in the drift. The risk-neutral dynamics are dF = σF dW under the T-forward "
        "measure. The closed-form solution is: "
        "C = exp(-rT)[F·N(d1) - K·N(d2)] for a call, "
        "P = exp(-rT)[K·N(-d2) - F·N(-d1)] for a put, "
        "where d1 = [ln(F/K) + σ²T/2] / (σ√T) and d2 = d1 - σ√T. "
        "Black-76 is the industry standard for CME-traded energy, metals, and "
        "agricultural options. It also underpins interest rate cap/floor pricing. "
        "Full analytical Greeks are available in closed form."
    )

    when_to_use = [
        "European options on exchange-traded commodity futures (WTI, Brent, gold, nat gas)",
        "When the futures price is directly observable and liquid",
        "Implying volatility from market option prices (commodity vol surface)",
        "Risk management: fast Greeks for large portfolios of commodity options",
        "Pricing commodity swaptions or Asian option lower bounds",
    ]
    when_not_to_use = [
        "American-style commodity options — need tree or LSM Monte Carlo",
        "When vol smile/skew is significant — use SABR or local vol",
        "Path-dependent payoffs (Asian, barrier) — use Monte Carlo",
        "When convenience yield or seasonality matters significantly",
        "Mean-reverting commodities at long maturities — use Schwartz model",
    ]
    assumptions = [
        "Futures price follows log-normal GBM: dF = σF dW (no drift under T-forward measure)",
        "Constant volatility σ and risk-free rate r",
        "European exercise only — no early exercise",
        "No transaction costs, margin calls, or daily settlement effects",
        "Liquidity: futures market is deep enough to hedge continuously",
    ]
    limitations = [
        "Log-normal futures prices cannot go negative (problem for natural gas spreads)",
        "No smile — one vol for all strikes at a given maturity",
        "Ignores mean reversion, which is important for long-dated commodity options",
        "Constant vol assumption unrealistic; commodity vol is often seasonal",
        "Does not capture convenience yield term structure or storage cost dynamics",
    ]

    formula_latex = (
        r"C = e^{-rT}\left[F N(d_1) - K N(d_2)\right],\quad"
        r"d_1 = \frac{\ln(F/K) + \frac{1}{2}\sigma^2 T}{\sigma\sqrt{T}},\quad"
        r"d_2 = d_1 - \sigma\sqrt{T}"
    )
    formula_plain = (
        "C = exp(-rT) * [F*N(d1) - K*N(d2)]  "
        "P = exp(-rT) * [K*N(-d2) - F*N(-d1)]  "
        "d1 = [ln(F/K) + 0.5*σ²*T] / (σ*√T)  "
        "d2 = d1 - σ*√T"
    )

    # ── Parameters ───────────────────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "futures_price", "Futures Price (F)",
                "Current commodity futures price",
                "float", 80.0, 0.01, None, 0.01, unit="$/unit",
            ),
            ParameterSpec(
                "strike", "Strike Price (K)",
                "Option strike price",
                "float", 80.0, 0.01, None, 0.01, unit="$/unit",
            ),
            ParameterSpec(
                "maturity", "Time to Expiry (T)",
                "Option time to expiration in years",
                "float", 0.5, 0.001, 10.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "vol", "Implied Volatility (σ)",
                "Annualized Black-76 implied volatility",
                "float", 0.30, 0.001, 5.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate (r)",
                "Continuous risk-free discount rate",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "option_type", "Option Type",
                "Call or put on the commodity future",
                "select", "call", options=["call", "put"],
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "WTI Crude Oil ATM Call (6M)": {
                "futures_price": 80.0, "strike": 80.0, "maturity": 0.5,
                "vol": 0.35, "r": 0.05, "option_type": "call",
            },
            "Gold Futures OTM Call (1Y)": {
                "futures_price": 2000.0, "strike": 2100.0, "maturity": 1.0,
                "vol": 0.18, "r": 0.05, "option_type": "call",
            },
            "Natural Gas ATM Put (3M)": {
                "futures_price": 2.80, "strike": 2.80, "maturity": 0.25,
                "vol": 0.65, "r": 0.05, "option_type": "put",
            },
            "Corn ITM Put (9M)": {
                "futures_price": 440.0, "strike": 460.0, "maturity": 0.75,
                "vol": 0.28, "r": 0.05, "option_type": "put",
            },
        }

    # ── Calculation ──────────────────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        F = float(params["futures_price"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["vol"])
        r = float(params["r"])
        opt_type = params.get("option_type", "call").lower()
        is_call = opt_type == "call"

        steps: list[CalculationStep] = []

        # ── Step 1: d1, d2 ───────────────────────────────────────────────────
        sqrt_T = math.sqrt(T)
        log_FK = math.log(F / K) if F > 0 and K > 0 else 0.0
        d1 = (log_FK + 0.5 * sigma ** 2 * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        df = math.exp(-r * T)

        steps.append(CalculationStep(
            step_number=1,
            label="Compute d1 and d2",
            formula=(
                r"d_1 = \frac{\ln(F/K) + \frac{1}{2}\sigma^2 T}{\sigma\sqrt{T}},\quad"
                r"d_2 = d_1 - \sigma\sqrt{T}"
            ),
            substitution=(
                f"F={F}, K={K}, σ={sigma}, T={T}Y.  "
                f"ln(F/K) = {log_FK:.6f},  σ²T/2 = {0.5*sigma**2*T:.6f}.  "
                f"σ√T = {sigma*sqrt_T:.6f}.  "
                f"d1 = {d1:.6f},  d2 = {d2:.6f}"
            ),
            result=round(d1, 6),
            explanation=(
                "d1 and d2 are the standardised log-moneyness terms. "
                "d1 > 0 means the option is in-the-money on a log scale. "
                "In Black-76 there is no carry term (futures require no investment)."
            ),
        ))

        # ── Step 2: N(d1), N(d2) ─────────────────────────────────────────────
        Nd1 = _norm_cdf(d1)
        Nd2 = _norm_cdf(d2)
        Nnd1 = _norm_cdf(-d1)
        Nnd2 = _norm_cdf(-d2)

        steps.append(CalculationStep(
            step_number=2,
            label="Normal CDF values",
            formula=r"N(d_1),\; N(d_2),\; N(-d_1),\; N(-d_2)",
            substitution=(
                f"N(d1) = N({d1:.4f}) = {Nd1:.6f}.  "
                f"N(d2) = N({d2:.4f}) = {Nd2:.6f}.  "
                f"N(-d1) = {Nnd1:.6f},  N(-d2) = {Nnd2:.6f}.  "
                f"Put-call check: N(d1)+N(-d1) = {Nd1+Nnd1:.6f} ≈ 1"
            ),
            result=round(Nd1, 6),
            explanation=(
                "N(d1) is the risk-neutral probability-weighted delta for the call. "
                "N(d2) is the risk-neutral probability that the option expires in-the-money."
            ),
        ))

        # ── Step 3: Option price ──────────────────────────────────────────────
        if is_call:
            price = df * (F * Nd1 - K * Nd2)
        else:
            price = df * (K * Nnd2 - F * Nnd1)

        intrinsic = max(F - K, 0.0) if is_call else max(K - F, 0.0)
        time_value = price - intrinsic * df

        steps.append(CalculationStep(
            step_number=3,
            label=f"Black-76 {'call' if is_call else 'put'} price",
            formula=(
                r"C = e^{-rT}\left[F N(d_1) - K N(d_2)\right]"
                if is_call else
                r"P = e^{-rT}\left[K N(-d_2) - F N(-d_1)\right]"
            ),
            substitution=(
                f"DF = e^{{-{r}×{T}}} = {df:.6f}.  "
                + (
                    f"C = {df:.4f} × [{F}×{Nd1:.4f} - {K}×{Nd2:.4f}] "
                    f"= {df:.4f} × {F*Nd1 - K*Nd2:.4f} = {price:.4f}"
                    if is_call else
                    f"P = {df:.4f} × [{K}×{Nnd2:.4f} - {F}×{Nnd1:.4f}] "
                    f"= {df:.4f} × {K*Nnd2 - F*Nnd1:.4f} = {price:.4f}"
                )
            ),
            result=round(price, 4),
            explanation=(
                f"Black-76 {'call' if is_call else 'put'} premium in the same units as "
                "the futures price. The discount factor exp(-rT) reflects the time value "
                "of the premium only — not cost of carry (futures are carry-neutral)."
            ),
        ))

        # ── Step 4: Put-Call Parity ───────────────────────────────────────────
        # C - P = exp(-rT)(F - K) for futures
        if is_call:
            put_parity = price - df * (F - K)
            call_parity = price
        else:
            call_parity = price + df * (F - K)
            put_parity = price
        parity_check = call_parity - put_parity - df * (F - K)

        steps.append(CalculationStep(
            step_number=4,
            label="Put-call parity verification",
            formula=r"C - P = e^{-rT}(F - K)",
            substitution=(
                f"C = {call_parity:.4f},  P = {put_parity:.4f}.  "
                f"C - P = {call_parity - put_parity:.4f}.  "
                f"exp(-rT)(F-K) = {df:.4f}×({F}-{K}) = {df*(F-K):.4f}.  "
                f"Parity error = {parity_check:.2e}"
            ),
            result=round(parity_check, 8),
            explanation=(
                "For futures options, put-call parity is C - P = exp(-rT)(F-K). "
                "Unlike equity options, there is no spot price or dividend yield — "
                "the futures contract itself has zero net present value at inception."
            ),
        ))

        # ── Step 5: Greeks ────────────────────────────────────────────────────
        nd1_pdf = _norm_pdf(d1)
        delta = df * Nd1 if is_call else -df * Nnd1
        gamma = df * nd1_pdf / (F * sigma * sqrt_T) if F > 0 and sigma > 0 and T > 0 else 0.0
        vega = F * df * nd1_pdf * sqrt_T  # per unit vol
        vega_1pct = vega / 100.0          # per 1% vol move
        theta_ann = -(F * df * nd1_pdf * sigma / (2.0 * sqrt_T)) - r * price if T > 0 else 0.0
        theta_day = theta_ann / 365.0
        rho_ann = -T * price  # per unit rate (simplified for futures: rho ≈ -T*price)

        steps.append(CalculationStep(
            step_number=5,
            label="Analytical Greeks",
            formula=(
                r"\Delta = e^{-rT}N(d_1),\quad"
                r"\Gamma = \frac{e^{-rT} N'(d_1)}{F\sigma\sqrt{T}},\quad"
                r"\mathcal{V} = F e^{-rT} N'(d_1)\sqrt{T}"
            ),
            substitution=(
                f"N'(d1) = {nd1_pdf:.6f}.  "
                f"Δ = {delta:.6f},  Γ = {gamma:.6f},  "
                f"Vega = {vega:.4f} per unit σ ({vega_1pct:.4f} per 1%),  "
                f"Θ = {theta_day:.4f}/day,  ρ ≈ {rho_ann:.4f} per unit r"
            ),
            result=round(delta, 6),
            explanation=(
                "All Greeks are in closed form. Delta is the futures delta (no "
                "discounting of underlying since futures require no investment). "
                "Vega per 1% vol move is useful for vol trading. "
                "Theta is per calendar day (divided by 365)."
            ),
        ))

        # ── Step 6: Moneyness & vol context ──────────────────────────────────
        moneyness = F / K
        log_moneyness = math.log(moneyness) if moneyness > 0 else 0.0
        forward_delta = Nd1 if is_call else -Nnd1
        delta_pct = abs(forward_delta) * 100

        steps.append(CalculationStep(
            step_number=6,
            label="Moneyness, delta-strike mapping & vol context",
            formula=r"\text{Moneyness} = F/K,\quad \Delta\text{-strike: } K = F e^{-\sigma\sqrt{T}\,\Phi^{-1}(\Delta e^{rT})}",
            substitution=(
                f"F/K = {moneyness:.4f},  ln(F/K) = {log_moneyness:.4f}.  "
                f"Option delta = {delta_pct:.1f}Δ.  "
                f"Time value = {time_value:.4f},  intrinsic (undiscounted) = {intrinsic:.4f}.  "
                f"Vol×√T (total vol) = {sigma*sqrt_T:.4f}"
            ),
            result=round(moneyness, 4),
            explanation=(
                "Commodity options are quoted by delta (e.g., 25Δ put) on vol surfaces. "
                "Total vol σ√T measures the total uncertainty over the option life — "
                "useful for comparing options of different maturities. "
                "Higher total vol → fatter tails → higher option premiums."
            ),
        ))

        return SimulatorResult(
            fair_value=round(price, 4),
            method="Black-76 (log-normal futures)",
            greeks={
                "delta": round(delta, 6),
                "gamma": round(gamma, 6),
                "vega_1pct": round(vega_1pct, 4),
                "theta_day": round(theta_day, 4),
                "rho": round(rho_ann, 4),
            },
            calculation_steps=steps,
            diagnostics={
                "d1": round(d1, 6),
                "d2": round(d2, 6),
                "N_d1": round(Nd1, 6),
                "N_d2": round(Nd2, 6),
                "discount_factor": round(df, 6),
                "intrinsic_value": round(intrinsic, 4),
                "time_value": round(time_value, 4),
                "moneyness_F_over_K": round(moneyness, 4),
                "total_vol_sigma_sqrt_T": round(sigma * sqrt_T, 4),
                "call_price": round(call_parity, 4),
                "put_price": round(put_parity, 4),
                "put_call_parity_error": round(abs(parity_check), 10),
            },
        )
