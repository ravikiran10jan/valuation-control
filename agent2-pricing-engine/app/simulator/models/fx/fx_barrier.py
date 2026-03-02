"""FX Barrier Option pricing — analytical formulas for single barriers.

Prices knock-in and knock-out barrier options using closed-form
solutions (Merton/Reiner-Rubinstein) extended to FX via Garman-Kohlhagen.
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


def _gk_price(S, K, T, sigma, rd, rf, opt):
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (rd - rf + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    df_f = math.exp(-rf * T)
    df_d = math.exp(-rd * T)
    if opt == "call":
        return S * df_f * norm.cdf(d1) - K * df_d * norm.cdf(d2)
    return K * df_d * norm.cdf(-d2) - S * df_f * norm.cdf(-d1)


@ModelRegistry.register
class FXBarrierModel(BaseSimulatorModel):

    model_id = "fx_barrier"
    model_name = "FX Barrier Option"
    product_type = "FX Barrier Option"
    asset_class = "fx"

    short_description = "Analytical knock-in / knock-out FX barrier option pricing"
    long_description = (
        "Prices single-barrier FX options using the closed-form formulas of "
        "Reiner & Rubinstein (1991), extended to the Garman-Kohlhagen FX framework. "
        "Supports four barrier types: down-and-out, down-and-in, up-and-out, and "
        "up-and-in for both calls and puts. The in-out parity (knock-in + knock-out "
        "= vanilla) provides a built-in cross-check. An optional cash rebate is paid "
        "if the barrier is hit (for knock-outs) or not hit (for knock-ins)."
    )

    when_to_use = [
        "FX barrier options with continuous barrier monitoring (analytical)",
        "Quick pricing of standard single-barrier structures",
        "In-out parity verification for risk management",
        "When barrier is not too close to spot (avoids pin risk)",
    ]
    when_not_to_use = [
        "Discrete barrier monitoring — use MC with Broadie-Glasserman correction",
        "Double barriers (knock-out range) — use PDE or MC",
        "Window barriers, Parisian barriers — use MC",
        "When vol smile matters near the barrier — use local vol",
    ]
    assumptions = [
        "Spot follows GBM: dS = (r_d - r_f)S dt + σS dW",
        "Continuous barrier monitoring (not discrete fixings)",
        "Constant volatility, domestic and foreign rates",
        "No credit risk on the counterparty",
    ]
    limitations = [
        "Continuous monitoring overstates barrier hit probability vs discrete",
        "Flat vol — barrier options are very sensitive to smile/skew",
        "Greeks can be discontinuous near the barrier",
        "Does not handle gap risk at barrier level",
    ]

    formula_latex = (
        r"V_{out} = V_{vanilla} - V_{in}"
        r"\quad"
        r"V_{in} \text{ uses } (H/S)^{2\lambda} \text{ reflection terms}"
    )
    formula_plain = (
        "Knock-out = Vanilla - Knock-in (in-out parity).  "
        "λ = (r_d - r_f + σ²/2) / σ².  "
        "Barrier terms involve (H/S)^(2λ) reflection factors."
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Spot Rate (S)", "Spot FX rate (DOM/FOR)",
                "float", 1.0800, 0.0001, None, 0.0001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "strike", "Strike (K)", "Option strike",
                "float", 1.0800, 0.0001, None, 0.0001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "barrier", "Barrier (H)", "Barrier level",
                "float", 1.0400, 0.0001, None, 0.0001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "maturity", "Time to Expiry (T)", "Option maturity in years",
                "float", 0.5, 0.01, 30.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "vol", "Volatility (σ)", "Annualized implied volatility",
                "float", 0.08, 0.001, 5.0, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "r_dom", "Domestic Rate (r_d)", "Domestic risk-free rate",
                "float", 0.053, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "r_for", "Foreign Rate (r_f)", "Foreign risk-free rate",
                "float", 0.035, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "option_type", "Option Type", "Call or Put",
                "select", "put", options=["call", "put"],
            ),
            ParameterSpec(
                "barrier_type", "Barrier Type", "Knock-in or knock-out, up or down",
                "select", "down_and_out",
                options=["down_and_out", "down_and_in", "up_and_out", "up_and_in"],
            ),
            ParameterSpec(
                "rebate", "Rebate", "Cash rebate if barrier is triggered (per unit FOR)",
                "float", 0.0, 0.0, None, 0.001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "notional", "Notional", "Foreign currency notional",
                "float", 1_000_000.0, 1.0, None, 1000.0, unit="FOR",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "EURUSD Down-and-Out Put 6M": {
                "spot": 1.0800, "strike": 1.0800, "barrier": 1.0400,
                "maturity": 0.5, "vol": 0.08,
                "r_dom": 0.053, "r_for": 0.035,
                "option_type": "put", "barrier_type": "down_and_out",
                "rebate": 0.0, "notional": 1_000_000.0,
            },
            "USDJPY Up-and-Out Call 3M": {
                "spot": 155.50, "strike": 155.50, "barrier": 162.00,
                "maturity": 0.25, "vol": 0.10,
                "r_dom": 0.001, "r_for": 0.053,
                "option_type": "call", "barrier_type": "up_and_out",
                "rebate": 0.0, "notional": 10_000_000.0,
            },
            "GBPUSD Down-and-In Put 1Y": {
                "spot": 1.2700, "strike": 1.2500, "barrier": 1.2000,
                "maturity": 1.0, "vol": 0.09,
                "r_dom": 0.053, "r_for": 0.05,
                "option_type": "put", "barrier_type": "down_and_in",
                "rebate": 0.0, "notional": 5_000_000.0,
            },
            "EURUSD Up-and-In Call 6M (with rebate)": {
                "spot": 1.0800, "strike": 1.1000, "barrier": 1.1200,
                "maturity": 0.5, "vol": 0.08,
                "r_dom": 0.053, "r_for": 0.035,
                "option_type": "call", "barrier_type": "up_and_in",
                "rebate": 0.005, "notional": 1_000_000.0,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        K = float(params["strike"])
        H = float(params["barrier"])
        T = float(params["maturity"])
        sigma = float(params["vol"])
        rd = float(params["r_dom"])
        rf = float(params["r_for"])
        opt_type = params.get("option_type", "put").lower()
        bar_type = params.get("barrier_type", "down_and_out").lower()
        rebate = float(params.get("rebate", 0.0))
        notional = float(params.get("notional", 1_000_000.0))

        is_call = opt_type == "call"
        is_down = "down" in bar_type
        is_out = "out" in bar_type
        steps: list[CalculationStep] = []
        sqrt_T = math.sqrt(T)

        # Step 1: key parameters
        mu = (rd - rf) / (sigma**2) - 0.5
        lam = math.sqrt(mu**2 + 2 * rd / (sigma**2))
        phi = 1 if is_call else -1

        steps.append(CalculationStep(
            step_number=1,
            label="Barrier parameters",
            formula=r"\mu = \frac{r_d - r_f}{\sigma^2} - \frac{1}{2},\quad \lambda = \sqrt{\mu^2 + \frac{2r_d}{\sigma^2}}",
            substitution=(
                f"μ = ({rd}-{rf})/{sigma}² - 0.5 = {mu:.6f},  "
                f"λ = {lam:.6f},  H/S = {H / S:.6f},  "
                f"{'Down' if is_down else 'Up'}-and-{'Out' if is_out else 'In'} "
                f"{'Call' if is_call else 'Put'}"
            ),
            result=round(mu, 6),
            explanation=(
                "μ and λ are the key parameters for barrier reflection terms. "
                "The ratio H/S determines how close spot is to the barrier."
            ),
        ))

        # Step 2: vanilla price
        vanilla = _gk_price(S, K, T, sigma, rd, rf, opt_type)
        steps.append(CalculationStep(
            step_number=2,
            label="Vanilla GK price",
            formula=r"V_{vanilla} = \text{GK}(S, K, T, \sigma, r_d, r_f)",
            substitution=f"Vanilla {opt_type} = {vanilla:.6f}",
            result=round(vanilla, 6),
            explanation="Standard Garman-Kohlhagen price without barrier.",
        ))

        # Step 3: compute barrier option via Reiner-Rubinstein formulas
        # Using the decomposition into terms A through F
        df_d = math.exp(-rd * T)
        df_f = math.exp(-rf * T)

        def _N(x):
            return norm.cdf(x)

        x1 = math.log(S / K) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T
        x2 = math.log(S / H) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T
        y1 = math.log(H**2 / (S * K)) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T
        y2 = math.log(H / S) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T

        # Standard barrier terms
        A = phi * S * df_f * _N(phi * x1) - phi * K * df_d * _N(phi * (x1 - sigma * sqrt_T))
        B = phi * S * df_f * _N(phi * x2) - phi * K * df_d * _N(phi * (x2 - sigma * sqrt_T))
        C = (phi * S * df_f * (H / S)**(2 * (mu + 1)) * _N(-phi * y1)
             - phi * K * df_d * (H / S)**(2 * mu) * _N(-phi * (y1 - sigma * sqrt_T)))
        D = (phi * S * df_f * (H / S)**(2 * (mu + 1)) * _N(-phi * y2)
             - phi * K * df_d * (H / S)**(2 * mu) * _N(-phi * (y2 - sigma * sqrt_T)))

        # Rebate terms
        if rebate > 0:
            z1 = math.log(H / S) / (sigma * sqrt_T) + lam * sigma * sqrt_T
            z2 = math.log(H / S) / (sigma * sqrt_T) - lam * sigma * sqrt_T
            rebate_out = rebate * df_d * (
                (H / S)**(mu + lam) * _N(-phi * z1 if is_down else phi * z1) +
                (H / S)**(mu - lam) * _N(-phi * z2 if is_down else phi * z2)
            ) if is_out else rebate * df_d * (
                1.0 - (H / S)**(mu + lam) * _N(-phi * z1 if is_down else phi * z1) -
                (H / S)**(mu - lam) * _N(-phi * z2 if is_down else phi * z2)
            )
        else:
            rebate_out = 0.0

        # Combine terms based on barrier type
        # Down barriers: H < S.  Up barriers: H > S.
        if is_down and is_call:
            if K > H:
                # Down-and-out call (K > H): A - C + rebate
                barrier_price = A - C
                if is_out:
                    price = barrier_price + rebate_out
                else:
                    price = vanilla - barrier_price + rebate_out
            else:
                # Down-and-out call (K <= H): B - D + rebate
                barrier_price = B - D
                if is_out:
                    price = barrier_price + rebate_out
                else:
                    price = vanilla - barrier_price + rebate_out
        elif is_down and not is_call:
            if K > H:
                # Down-and-out put (K > H): A - B + D - C + rebate
                barrier_price = A - B + D - C
                if is_out:
                    price = barrier_price + rebate_out
                else:
                    price = vanilla - barrier_price + rebate_out
            else:
                # Down-and-out put (K <= H): 0 + rebate (always knocked out before ITM)
                if is_out:
                    price = rebate_out
                else:
                    price = vanilla + rebate_out
        elif not is_down and is_call:
            if K > H:
                # Up-and-out call (K > H): 0 + rebate
                if is_out:
                    price = rebate_out
                else:
                    price = vanilla + rebate_out
            else:
                # Up-and-out call (K <= H): A - B + D - C + rebate
                barrier_price = A - B + D - C
                if is_out:
                    price = barrier_price + rebate_out
                else:
                    price = vanilla - barrier_price + rebate_out
        else:  # up and put
            if K > H:
                # Up-and-out put (K > H): B - D + rebate
                barrier_price = B - D
                if is_out:
                    price = barrier_price + rebate_out
                else:
                    price = vanilla - barrier_price + rebate_out
            else:
                # Up-and-out put (K <= H): A - C + rebate
                barrier_price = A - C
                if is_out:
                    price = barrier_price + rebate_out
                else:
                    price = vanilla - barrier_price + rebate_out

        price = max(price, 0.0)

        steps.append(CalculationStep(
            step_number=3,
            label="Barrier option price",
            formula=(
                r"V_{out} = \text{combination of A,B,C,D terms}"
                r"\quad V_{in} = V_{vanilla} - V_{out}"
            ),
            substitution=(
                f"A={A:.6f}, B={B:.6f}, C={C:.6f}, D={D:.6f}.  "
                f"Rebate component = {rebate_out:.6f}.  "
                f"Barrier {bar_type.replace('_', '-')} price = {price:.6f}"
            ),
            result=round(price, 6),
            explanation=(
                "Reiner-Rubinstein decomposition into terms A-D, combined "
                "according to the specific barrier type and strike/barrier relationship."
            ),
        ))

        # Step 4: in-out parity check
        if is_out:
            implied_in = vanilla - price + rebate_out
            parity_label = "Implied knock-in"
        else:
            implied_out = vanilla - price + rebate_out
            parity_label = "Implied knock-out"

        steps.append(CalculationStep(
            step_number=4,
            label="In-out parity check",
            formula=r"V_{in} + V_{out} = V_{vanilla} \;(+\; \text{rebate terms})",
            substitution=(
                f"Vanilla = {vanilla:.6f},  "
                f"{'Knock-out' if is_out else 'Knock-in'} = {price:.6f},  "
                f"{parity_label} = {(implied_in if is_out else implied_out):.6f}.  "
                f"Sum = {price + (implied_in if is_out else implied_out):.6f}"
            ),
            result=round(vanilla, 6),
            explanation=(
                "In-out parity: the sum of a knock-in and knock-out with the "
                "same barrier equals the vanilla option price."
            ),
        ))

        # Step 5: barrier distance and probability
        barrier_dist_pct = (H / S - 1) * 100
        # Approximate probability of hitting barrier (for down: P(min(S) < H))
        drift = rd - rf - 0.5 * sigma**2
        if is_down and H < S:
            z_bar = (math.log(H / S) - drift * T) / (sigma * sqrt_T)
            p_hit = norm.cdf(z_bar) + math.exp(2 * drift * math.log(H / S) / sigma**2) * norm.cdf(z_bar + 2 * math.log(H / S) / (sigma * sqrt_T))
        elif not is_down and H > S:
            z_bar = (math.log(H / S) - drift * T) / (sigma * sqrt_T)
            p_hit = norm.cdf(-z_bar) + math.exp(2 * drift * math.log(H / S) / sigma**2) * norm.cdf(-z_bar + 2 * math.log(H / S) / (sigma * sqrt_T))
        else:
            p_hit = 1.0  # barrier already breached

        p_hit = min(max(p_hit, 0.0), 1.0)

        steps.append(CalculationStep(
            step_number=5,
            label="Barrier distance and hit probability",
            formula=r"P(\text{hit}) \approx \Phi(z) + e^{2\mu\ln(H/S)/\sigma^2}\Phi(z')",
            substitution=(
                f"Barrier distance = {barrier_dist_pct:.2f}%.  "
                f"P(barrier hit) ≈ {p_hit * 100:.2f}%.  "
                f"P(survive) ≈ {(1 - p_hit) * 100:.2f}%"
            ),
            result=round(p_hit * 100, 2),
            explanation=(
                "Approximate probability that spot touches the barrier during "
                "the option's life under GBM. Closer barriers have higher hit probability."
            ),
        ))

        # Step 6: Greeks via finite differences
        bump_s = 0.0001 * S
        p_up = self._reprice(S + bump_s, K, H, T, sigma, rd, rf, opt_type, bar_type, rebate)
        p_dn = self._reprice(S - bump_s, K, H, T, sigma, rd, rf, opt_type, bar_type, rebate)
        delta = (p_up - p_dn) / (2 * bump_s)
        gamma = (p_up - 2 * price + p_dn) / (bump_s**2)

        p_vup = self._reprice(S, K, H, T, sigma + 0.01, rd, rf, opt_type, bar_type, rebate)
        vega = p_vup - price

        greeks = {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "vega_1pct": round(vega, 6),
        }

        premium = price * notional

        steps.append(CalculationStep(
            step_number=6,
            label="Greeks and premium",
            formula=r"\Delta = \frac{V(S+\epsilon) - V(S-\epsilon)}{2\epsilon}",
            substitution=(
                f"Δ={delta:.6f}  Γ={gamma:.4f}  Vega={vega:.6f}/1%vol.  "
                f"Total premium = {premium:,.2f} DOM"
            ),
            result=round(delta, 6),
            explanation=(
                "Barrier Greeks can be discontinuous near the barrier. "
                "Delta can change sign and gamma can spike."
            ),
        ))

        return SimulatorResult(
            fair_value=round(price, 6),
            method="Reiner-Rubinstein (Analytical Barrier)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "vanilla_price": round(vanilla, 6),
                "barrier_price": round(price, 6),
                "barrier_discount": round((1 - price / vanilla) * 100 if vanilla > 0 else 0, 2),
                "barrier_distance_pct": round(barrier_dist_pct, 2),
                "hit_probability_pct": round(p_hit * 100, 2),
                "total_premium": round(premium, 2),
                "in_out_parity_vanilla": round(vanilla, 6),
                "barrier_type": bar_type,
            },
        )

    def _reprice(self, S, K, H, T, sigma, rd, rf, opt_type, bar_type, rebate):
        """Quick reprice for Greeks."""
        is_call = opt_type == "call"
        is_down = "down" in bar_type
        is_out = "out" in bar_type
        phi = 1 if is_call else -1
        sqrt_T = math.sqrt(T)
        mu = (rd - rf) / (sigma**2) - 0.5
        lam = math.sqrt(mu**2 + 2 * rd / (sigma**2))
        df_d = math.exp(-rd * T)
        df_f = math.exp(-rf * T)

        x1 = math.log(S / K) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T
        x2 = math.log(S / H) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T
        y1 = math.log(H**2 / (S * K)) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T
        y2 = math.log(H / S) / (sigma * sqrt_T) + (1 + mu) * sigma * sqrt_T

        N = norm.cdf
        A = phi * S * df_f * N(phi * x1) - phi * K * df_d * N(phi * (x1 - sigma * sqrt_T))
        B = phi * S * df_f * N(phi * x2) - phi * K * df_d * N(phi * (x2 - sigma * sqrt_T))
        C = (phi * S * df_f * (H / S)**(2 * (mu + 1)) * N(-phi * y1)
             - phi * K * df_d * (H / S)**(2 * mu) * N(-phi * (y1 - sigma * sqrt_T)))
        D = (phi * S * df_f * (H / S)**(2 * (mu + 1)) * N(-phi * y2)
             - phi * K * df_d * (H / S)**(2 * mu) * N(-phi * (y2 - sigma * sqrt_T)))

        vanilla = _gk_price(S, K, T, sigma, rd, rf, opt_type)
        rebate_out = 0.0

        if is_down and is_call:
            bp = A - C if K > H else B - D
            price = bp if is_out else vanilla - bp
        elif is_down and not is_call:
            if K > H:
                bp = A - B + D - C
                price = bp if is_out else vanilla - bp
            else:
                price = 0.0 if is_out else vanilla
        elif not is_down and is_call:
            if K > H:
                price = 0.0 if is_out else vanilla
            else:
                bp = A - B + D - C
                price = bp if is_out else vanilla - bp
        else:
            bp = B - D if K > H else A - C
            price = bp if is_out else vanilla - bp

        return max(price + rebate_out, 0.0)
