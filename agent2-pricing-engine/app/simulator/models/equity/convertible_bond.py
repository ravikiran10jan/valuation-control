"""Convertible Bond pricing via Tsiveriotis-Fernandes with credit.

Decomposes the CB into equity and debt components, solving a PDE
with different discount rates for each.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


@ModelRegistry.register
class ConvertibleBondModel(BaseSimulatorModel):

    model_id = "convertible_bond"
    model_name = "Convertible Bond (TF Model)"
    product_type = "Convertible Bond"
    asset_class = "equity"

    short_description = (
        "Tsiveriotis-Fernandes convertible bond pricing with credit risk"
    )
    long_description = (
        "Prices convertible bonds using the Tsiveriotis-Fernandes (1998) method. "
        "The CB value is split into an equity component (discounted at the risk-free "
        "rate) and a debt component (discounted at the risky rate = risk-free + credit "
        "spread). A binomial tree on the stock price determines optimal conversion. "
        "At each node: the holder converts to equity if the conversion value exceeds "
        "the continuation value, and the issuer may call if the CB exceeds the call "
        "price. This captures the interplay between equity upside, credit risk, and "
        "optionality."
    )

    when_to_use = [
        "Pricing convertible bonds with credit risk",
        "When you need the equity/debt decomposition for accounting",
        "Understanding how credit spread affects CB pricing",
        "Bonds with call provisions and conversion features",
    ]
    when_not_to_use = [
        "When stochastic interest rates matter (use 2-factor model)",
        "Mandatory convertibles (different structure)",
        "When detailed credit modeling is needed (use structural model)",
        "Highly path-dependent features (reset convertibles, etc.)",
    ]
    assumptions = [
        "Stock follows GBM: dS = (r-q)S dt + σS dW",
        "Flat credit spread added to risk-free rate for debt discounting",
        "Continuous dividend yield",
        "European or American conversion (checked at each node)",
        "Optional issuer call at a fixed call price",
    ]
    limitations = [
        "Single-factor (stock only) — no stochastic rates",
        "Flat credit spread — no term structure of credit",
        "No dilution effect from conversion",
        "Simplified call/put provisions",
    ]

    formula_latex = (
        r"V = V_{equity} + V_{debt}"
        r"\quad V_{equity} \text{ discounted at } r"
        r"\quad V_{debt} \text{ discounted at } r + s"
    )
    formula_plain = (
        "CB = Equity component + Debt component.  "
        "Equity part (conversion) discounted at r.  "
        "Debt part (coupons + principal) discounted at r + credit spread.  "
        "At each node: max(conversion value, continuation value)."
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Stock Price (S)", "Current stock price",
                "float", 50.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "face_value", "Face Value", "Bond face/par value",
                "float", 100.0, 1.0, None, 1.0, unit="$",
            ),
            ParameterSpec(
                "conversion_ratio", "Conversion Ratio", "Number of shares per bond",
                "float", 2.0, 0.01, 100.0, 0.01,
            ),
            ParameterSpec(
                "maturity", "Maturity (T)", "Time to maturity in years",
                "float", 5.0, 0.1, 30.0, 0.1, unit="years",
            ),
            ParameterSpec(
                "coupon_rate", "Coupon Rate", "Annual coupon rate (decimal)",
                "float", 0.02, 0.0, 0.2, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "vol", "Stock Vol (σ)", "Annualized stock volatility",
                "float", 0.30, 0.01, 3.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate", "Continuous risk-free rate",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "q", "Dividend Yield", "Continuous dividend yield",
                "float", 0.01, 0.0, 0.3, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "credit_spread", "Credit Spread", "Issuer credit spread (decimal)",
                "float", 0.02, 0.0, 0.3, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "call_price", "Call Price", "Issuer call price (0 = no call)",
                "float", 110.0, 0.0, None, 1.0, unit="$",
            ),
            ParameterSpec(
                "n_steps", "Tree Steps", "Number of tree steps",
                "int", 200, 20, 1000, 10,
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "Standard CB (no call)": {
                "spot": 50.0, "face_value": 100.0, "conversion_ratio": 2.0,
                "maturity": 5.0, "coupon_rate": 0.02, "vol": 0.30,
                "r": 0.05, "q": 0.01, "credit_spread": 0.02,
                "call_price": 0.0, "n_steps": 200,
            },
            "Callable CB": {
                "spot": 50.0, "face_value": 100.0, "conversion_ratio": 2.0,
                "maturity": 5.0, "coupon_rate": 0.02, "vol": 0.30,
                "r": 0.05, "q": 0.01, "credit_spread": 0.02,
                "call_price": 110.0, "n_steps": 200,
            },
            "Deep ITM (high stock price)": {
                "spot": 80.0, "face_value": 100.0, "conversion_ratio": 2.0,
                "maturity": 5.0, "coupon_rate": 0.02, "vol": 0.30,
                "r": 0.05, "q": 0.01, "credit_spread": 0.02,
                "call_price": 0.0, "n_steps": 200,
            },
            "High credit spread (distressed)": {
                "spot": 50.0, "face_value": 100.0, "conversion_ratio": 2.0,
                "maturity": 5.0, "coupon_rate": 0.04, "vol": 0.40,
                "r": 0.05, "q": 0.01, "credit_spread": 0.08,
                "call_price": 0.0, "n_steps": 200,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S0 = float(params["spot"])
        face = float(params["face_value"])
        cr = float(params["conversion_ratio"])
        T = float(params["maturity"])
        coupon_rate = float(params.get("coupon_rate", 0.02))
        sigma = float(params["vol"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        cs = float(params.get("credit_spread", 0.02))
        call_price = float(params.get("call_price", 0.0))
        N = int(params.get("n_steps", 200))
        has_call = call_price > 0

        steps: list[CalculationStep] = []
        dt = T / N

        # Tree parameters
        u = math.exp(sigma * math.sqrt(dt))
        d = 1.0 / u
        p = (math.exp((r - q) * dt) - d) / (u - d)
        disc_rf = math.exp(-r * dt)
        disc_risky = math.exp(-(r + cs) * dt)
        coupon_per_step = coupon_rate * face * dt  # continuous approximation

        # Conversion price
        conv_price = face / cr

        steps.append(CalculationStep(
            step_number=1,
            label="Setup",
            formula=(
                r"u = e^{\sigma\sqrt{dt}},\; d=1/u,\; "
                r"\text{conv price} = \text{face}/\text{CR}"
            ),
            substitution=(
                f"u={u:.6f}, d={d:.6f}, p={p:.6f}.  "
                f"Conversion price = {face}/{cr} = ${conv_price:.2f}.  "
                f"Current parity = CR×S = {cr}×{S0} = ${cr * S0:.2f}.  "
                f"Credit spread = {cs * 100:.1f}%, "
                f"{'Callable at $' + f'{call_price:.0f}' if has_call else 'Not callable'}"
            ),
            result=round(conv_price, 2),
            explanation=(
                "Conversion price is the effective stock price paid when converting. "
                "Parity is the current conversion value."
            ),
        ))

        # Build terminal values
        j_arr = np.arange(N + 1)
        S_term = S0 * (u ** (N - j_arr)) * (d ** j_arr)
        conv_val = cr * S_term
        # At maturity: holder converts if conv_val > face + final coupon
        bond_val = face + coupon_rate * face  # final coupon
        V = np.maximum(conv_val, bond_val)
        # Equity component: portion that is conversion
        V_eq = np.where(conv_val >= bond_val, V, 0.0)
        V_debt = V - V_eq

        steps.append(CalculationStep(
            step_number=2,
            label="Terminal payoff",
            formula=(
                r"V_T = \max(\text{CR} \times S_T,\; \text{face} + \text{coupon})"
            ),
            substitution=(
                f"S ranges from {S_term[0]:.2f} to {S_term[-1]:.4f}.  "
                f"Conversion ITM nodes: {int(np.sum(conv_val >= bond_val))}/{N + 1}"
            ),
            result=round(float(V[N // 2]), 2),
            explanation="At maturity: convert to shares or take face + final coupon.",
        ))

        # Backward induction with TF decomposition
        convert_nodes = 0
        call_nodes = 0

        for i in range(N - 1, -1, -1):
            # Continuation value
            V_eq_cont = disc_rf * (p * V_eq[:i + 1] + (1 - p) * V_eq[1:i + 2])
            V_debt_cont = disc_risky * (p * V_debt[:i + 1] + (1 - p) * V_debt[1:i + 2])
            V_cont = V_eq_cont + V_debt_cont + coupon_per_step

            # Stock prices at this step
            j_idx = np.arange(i + 1)
            S_nodes = S0 * (u ** (i - j_idx)) * (d ** j_idx)
            conv_now = cr * S_nodes

            # Conversion: holder converts if conv_val > continuation
            convert = conv_now > V_cont
            convert_nodes += int(np.sum(convert))

            V_new = np.where(convert, conv_now, V_cont)
            V_eq_new = np.where(convert, conv_now, V_eq_cont)
            V_debt_new = np.where(convert, 0.0, V_debt_cont + coupon_per_step)

            # Issuer call: if callable and V > call_price, issuer calls
            if has_call:
                called = V_new > call_price
                # When called, holder can still convert
                call_or_convert = np.maximum(conv_now, call_price)
                V_new = np.where(called, call_or_convert, V_new)
                V_eq_new = np.where(
                    called & (conv_now >= call_price), conv_now,
                    np.where(called, 0.0, V_eq_new)
                )
                V_debt_new = np.where(
                    called & (conv_now < call_price), call_price,
                    np.where(called, 0.0, V_debt_new)
                )
                call_nodes += int(np.sum(called & ~convert))

            V = V_new
            V_eq = V_eq_new
            V_debt = V_debt_new

        cb_price = float(V[0])
        equity_comp = float(V_eq[0])
        debt_comp = float(V_debt[0])

        steps.append(CalculationStep(
            step_number=3,
            label="Backward induction (TF decomposition)",
            formula=(
                r"V_{equity} \text{ disc at } r,\quad V_{debt} \text{ disc at } r+s"
            ),
            substitution=(
                f"CB Price = ${cb_price:.4f}.  "
                f"Equity component = ${equity_comp:.4f},  "
                f"Debt component = ${debt_comp:.4f}.  "
                f"Conversion nodes = {convert_nodes}"
                + (f",  Call nodes = {call_nodes}" if has_call else "")
            ),
            result=round(cb_price, 4),
            explanation=(
                "Equity flows (conversion) are discounted at the risk-free rate; "
                "debt flows (coupons, principal) at the risky rate."
            ),
        ))

        # Step 4: risk metrics
        parity = cr * S0
        premium = (cb_price - parity) / parity * 100 if parity > 0 else 0

        # Straight bond value (no conversion)
        n_coupons = int(T)
        straight_bond = sum(
            coupon_rate * face * math.exp(-(r + cs) * t) for t in range(1, n_coupons + 1)
        ) + face * math.exp(-(r + cs) * T)

        steps.append(CalculationStep(
            step_number=4,
            label="Risk metrics",
            formula=r"\text{Premium} = \frac{CB - \text{Parity}}{\text{Parity}} \times 100\%",
            substitution=(
                f"Parity = CR×S = {parity:.2f}.  "
                f"CB price = {cb_price:.4f}.  "
                f"Conversion premium = {premium:.2f}%.  "
                f"Straight bond value = {straight_bond:.2f}"
            ),
            result=round(premium, 2),
            explanation=(
                "Conversion premium measures how much above parity the CB trades. "
                "Higher premium = more bond-like; lower premium = more equity-like."
            ),
        ))

        # Delta via bump
        bump = 0.01 * S0
        cb_up = self._reprice(S0 + bump, face, cr, T, coupon_rate, sigma, r, q, cs, call_price, N)
        cb_dn = self._reprice(S0 - bump, face, cr, T, coupon_rate, sigma, r, q, cs, call_price, N)
        delta = (cb_up - cb_dn) / (2 * bump)

        steps.append(CalculationStep(
            step_number=5,
            label="Delta",
            formula=r"\Delta = \frac{V(S+\epsilon) - V(S-\epsilon)}{2\epsilon}",
            substitution=f"Δ = ({cb_up:.4f} - {cb_dn:.4f}) / {2 * bump:.2f} = {delta:.6f}",
            result=round(delta, 6),
            explanation="CB delta: sensitivity of CB price to stock price changes.",
        ))

        return SimulatorResult(
            fair_value=round(cb_price, 4),
            method=f"Tsiveriotis-Fernandes Binomial ({N} steps)",
            greeks={
                "delta": round(delta, 6),
                "delta_shares": round(delta * cr, 6),
            },
            calculation_steps=steps,
            diagnostics={
                "cb_price": round(cb_price, 4),
                "equity_component": round(equity_comp, 4),
                "debt_component": round(debt_comp, 4),
                "parity": round(parity, 2),
                "conversion_premium_pct": round(premium, 2),
                "straight_bond_value": round(straight_bond, 2),
                "conversion_price": round(conv_price, 2),
                "n_steps": N,
            },
        )

    def _reprice(self, S0, face, cr, T, coupon_rate, sigma, r, q, cs, call_price, N):
        dt = T / N
        u = math.exp(sigma * math.sqrt(dt))
        d = 1.0 / u
        p = (math.exp((r - q) * dt) - d) / (u - d)
        disc_rf = math.exp(-r * dt)
        disc_risky = math.exp(-(r + cs) * dt)
        coupon_per_step = coupon_rate * face * dt
        has_call = call_price > 0

        j_arr = np.arange(N + 1)
        S_term = S0 * (u ** (N - j_arr)) * (d ** j_arr)
        conv_val = cr * S_term
        bond_val = face + coupon_rate * face
        V = np.maximum(conv_val, bond_val)
        V_eq = np.where(conv_val >= bond_val, V, 0.0)
        V_debt = V - V_eq

        for i in range(N - 1, -1, -1):
            V_eq_c = disc_rf * (p * V_eq[:i + 1] + (1 - p) * V_eq[1:i + 2])
            V_debt_c = disc_risky * (p * V_debt[:i + 1] + (1 - p) * V_debt[1:i + 2])
            V_cont = V_eq_c + V_debt_c + coupon_per_step
            j_idx = np.arange(i + 1)
            S_nodes = S0 * (u ** (i - j_idx)) * (d ** j_idx)
            conv_now = cr * S_nodes
            convert = conv_now > V_cont
            V = np.where(convert, conv_now, V_cont)
            V_eq = np.where(convert, conv_now, V_eq_c)
            V_debt = np.where(convert, 0.0, V_debt_c + coupon_per_step)
            if has_call:
                called = V > call_price
                V = np.where(called, np.maximum(conv_now, call_price), V)
                V_eq = np.where(called & (conv_now >= call_price), conv_now, np.where(called, 0.0, V_eq))
                V_debt = np.where(called & (conv_now < call_price), call_price, np.where(called, 0.0, V_debt))

        return float(V[0])
