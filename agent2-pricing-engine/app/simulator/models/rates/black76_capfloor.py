"""Black-76 model for interest rate Caps and Floors.

Each caplet/floorlet is priced as a European option on a forward rate
using the Black (1976) formula.  The cap/floor price is the sum of
individual caplet/floorlet prices.
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
class Black76CapFloorModel(BaseSimulatorModel):

    model_id = "black76_capfloor"
    model_name = "Black-76 Cap/Floor"
    product_type = "Interest Rate Cap / Floor"
    asset_class = "rates"

    short_description = "Cap and floor pricing via Black-76 on each forward rate"
    long_description = (
        "Prices interest rate caps and floors using the Black (1976) model. A cap "
        "is a portfolio of caplets, each of which is a call option on a forward "
        "LIBOR/SOFR rate. A floor is a portfolio of floorlets (put options on the "
        "forward rate). Each caplet is priced independently using Black-76 with the "
        "appropriate forward rate, discount factor, and volatility. The model uses "
        "flat (or per-caplet) volatilities. The total cap/floor price is the sum "
        "of all caplet/floorlet prices."
    )

    when_to_use = [
        "Pricing vanilla interest rate caps and floors",
        "Implying cap/floor volatilities from market prices",
        "Quick risk metrics (vega, delta) for cap/floor books",
        "When flat or spot volatilities are available for each tenor",
    ]
    when_not_to_use = [
        "When smile/skew across strikes matters — use SABR or local vol",
        "For CMS caps/floors — need convexity adjustment",
        "When negative rates are possible and log-normal breaks — use Bachelier",
        "For exotic caps (ratchet, sticky, etc.) — use term structure models",
    ]
    assumptions = [
        "Each forward rate is log-normally distributed (Black-76)",
        "Forward rates are independent across tenors (no term structure model)",
        "Flat or piecewise constant volatility surface",
        "Deterministic discount factors (OIS curve)",
        "No credit risk (clean pricing)",
    ]
    limitations = [
        "Log-normal model cannot handle negative rates (use Bachelier for that)",
        "No smile — same vol for all strikes at a given tenor",
        "Independent caplets — ignores correlation between forward rates",
        "Flat vol assumption may misprice short vs long caplets",
    ]

    formula_latex = (
        r"\text{Caplet}_i = \tau_i \cdot DF_i \cdot "
        r"\left[F_i N(d_1) - K N(d_2)\right]"
        r"\quad d_1 = \frac{\ln(F_i/K) + \frac{\sigma^2}{2} T_i}{\sigma \sqrt{T_i}}"
    )
    formula_plain = (
        "Caplet_i = τ_i × DF_i × [F_i × N(d1) - K × N(d2)],  "
        "Floorlet_i = τ_i × DF_i × [K × N(-d2) - F_i × N(-d1)],  "
        "d1 = [ln(F/K) + σ²T/2] / (σ√T),  d2 = d1 - σ√T"
    )

    # ── Parameters ──────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "notional", "Notional", "Cap/Floor notional amount",
                "float", 10_000_000.0, 1.0, None, 100_000.0, unit="$",
            ),
            ParameterSpec(
                "strike", "Strike Rate (K)", "Cap/Floor strike rate",
                "float", 0.05, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "maturity", "Cap/Floor Tenor", "Total maturity in years",
                "float", 3.0, 0.25, 30.0, 0.25, unit="years",
            ),
            ParameterSpec(
                "cap_or_floor", "Type", "Cap or Floor",
                "select", "cap", options=["cap", "floor"],
            ),
            ParameterSpec(
                "vol", "Flat Vol (σ)", "Flat Black implied volatility for all caplets",
                "float", 0.25, 0.001, 5.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "freq", "Reset Frequency", "Resets per year (4 = quarterly)",
                "int", 4, 1, 12, 1,
            ),
            ParameterSpec(
                "fwd_rate", "Forward Rate (flat)", "Flat forward rate assumption",
                "float", 0.048, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "ois_rate", "OIS Discount Rate", "Flat OIS rate for discounting",
                "float", 0.045, -0.05, 0.5, 0.001, unit="decimal",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "3Y ATM Cap (quarterly)": {
                "notional": 10_000_000.0, "strike": 0.048,
                "maturity": 3.0, "cap_or_floor": "cap",
                "vol": 0.25, "freq": 4,
                "fwd_rate": 0.048, "ois_rate": 0.045,
            },
            "5Y OTM Floor at 3%": {
                "notional": 50_000_000.0, "strike": 0.03,
                "maturity": 5.0, "cap_or_floor": "floor",
                "vol": 0.30, "freq": 4,
                "fwd_rate": 0.048, "ois_rate": 0.045,
            },
            "2Y ITM Cap at 4%": {
                "notional": 25_000_000.0, "strike": 0.04,
                "maturity": 2.0, "cap_or_floor": "cap",
                "vol": 0.20, "freq": 4,
                "fwd_rate": 0.048, "ois_rate": 0.045,
            },
            "10Y ATM Floor (semi-annual)": {
                "notional": 100_000_000.0, "strike": 0.045,
                "maturity": 10.0, "cap_or_floor": "floor",
                "vol": 0.28, "freq": 2,
                "fwd_rate": 0.045, "ois_rate": 0.043,
            },
        }

    # ── Calculation ────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        N = float(params["notional"])
        K = float(params["strike"])
        T = float(params["maturity"])
        is_cap = params.get("cap_or_floor", "cap").lower() == "cap"
        sigma = float(params["vol"])
        freq = int(params.get("freq", 4))
        F_flat = float(params.get("fwd_rate", 0.048))
        r_ois = float(params.get("ois_rate", 0.045))

        steps: list[CalculationStep] = []
        dt = 1.0 / freq
        n_caplets = int(round(T * freq)) - 1  # first period has no optionality

        steps.append(CalculationStep(
            step_number=1,
            label="Setup",
            formula=r"N_{caplets} = T \times freq - 1",
            substitution=(
                f"T = {T}Y, freq = {freq}/year, dt = {dt:.4f}Y.  "
                f"Caplets: {n_caplets} (first fixing is known, no optionality).  "
                f"Strike = {K*100:.3f}%, Flat fwd = {F_flat*100:.3f}%, "
                f"OIS = {r_ois*100:.3f}%, Vol = {sigma*100:.1f}%"
            ),
            result=n_caplets,
            explanation=(
                "A cap with T years and quarterly resets has T×freq - 1 caplets. "
                "The first period is already fixing (no option value)."
            ),
        ))

        # Step 2-3: price each caplet
        caplet_prices = []
        caplet_details = []
        total_delta = 0.0
        total_vega = 0.0

        for i in range(n_caplets):
            # Fixing time (option expiry) and payment time
            T_fix = (i + 1) * dt  # fixing at start of period i+1
            T_pay = (i + 2) * dt  # payment at end of period i+1
            df = math.exp(-r_ois * T_pay)
            F = F_flat  # using flat forward

            if K <= 0 or F <= 0:
                # Handle zero/negative rates: use intrinsic
                if is_cap:
                    caplet = dt * df * max(F - K, 0)
                else:
                    caplet = dt * df * max(K - F, 0)
                caplet_prices.append(caplet)
                caplet_details.append({
                    "period": i + 1, "T_fix": T_fix, "price": caplet,
                    "d1": 0, "d2": 0, "df": df,
                })
                continue

            sqrt_T = math.sqrt(T_fix)
            d1 = (math.log(F / K) + 0.5 * sigma**2 * T_fix) / (sigma * sqrt_T)
            d2 = d1 - sigma * sqrt_T

            if is_cap:
                caplet = dt * df * (F * norm.cdf(d1) - K * norm.cdf(d2))
                delta_i = dt * df * norm.cdf(d1)
            else:
                caplet = dt * df * (K * norm.cdf(-d2) - F * norm.cdf(-d1))
                delta_i = -dt * df * norm.cdf(-d1)

            vega_i = dt * df * F * norm.pdf(d1) * sqrt_T

            caplet_prices.append(caplet)
            total_delta += delta_i
            total_vega += vega_i
            caplet_details.append({
                "period": i + 1, "T_fix": round(T_fix, 4),
                "price": round(caplet, 8), "d1": round(d1, 6),
                "d2": round(d2, 6), "df": round(df, 6),
            })

        # Show first few caplet details
        n_show = min(4, n_caplets)
        detail_str = "  ".join(
            f"[{d['period']}] T={d['T_fix']:.2f}Y d1={d['d1']:.4f} "
            f"price={d['price']:.6f}"
            for d in caplet_details[:n_show]
        )

        steps.append(CalculationStep(
            step_number=2,
            label=f"Individual {'caplet' if is_cap else 'floorlet'} prices",
            formula=(
                r"c_i = \tau \cdot DF_{pay} \cdot [F \cdot N(d_1) - K \cdot N(d_2)]"
                if is_cap else
                r"f_i = \tau \cdot DF_{pay} \cdot [K \cdot N(-d_2) - F \cdot N(-d_1)]"
            ),
            substitution=detail_str + (f"  ... ({n_caplets} total)" if n_caplets > n_show else ""),
            result=round(caplet_prices[0] if caplet_prices else 0, 8),
            explanation=(
                f"Each {'caplet' if is_cap else 'floorlet'} is a Black-76 "
                f"{'call' if is_cap else 'put'} on the forward rate, "
                f"discounted to today and scaled by the accrual period."
            ),
        ))

        # Step 3: total price
        total_price_unit = sum(caplet_prices)
        total_price = total_price_unit * N

        steps.append(CalculationStep(
            step_number=3,
            label=f"Total {'Cap' if is_cap else 'Floor'} price",
            formula=(
                r"\text{Cap} = N \times \sum_{i=1}^{n} c_i"
                if is_cap else
                r"\text{Floor} = N \times \sum_{i=1}^{n} f_i"
            ),
            substitution=(
                f"Sum of {n_caplets} {'caplets' if is_cap else 'floorlets'} = "
                f"{total_price_unit:.8f} per unit.  "
                f"Total = {N:,.0f} × {total_price_unit:.8f} = {total_price:,.2f}"
            ),
            result=round(total_price, 2),
            explanation=f"Total {'cap' if is_cap else 'floor'} premium in dollar terms.",
        ))

        # Step 4: Greeks
        total_delta_dollar = total_delta * N
        total_vega_dollar = total_vega * N / 100  # per 1% vol move

        # Put-call parity check: Cap - Floor = swap (float - fixed)
        # Compute the corresponding swap value for diagnostics
        swap_value = 0.0
        for i in range(n_caplets):
            T_pay = (i + 2) * dt
            df = math.exp(-r_ois * T_pay)
            swap_value += dt * df * (F_flat - K)
        swap_value_dollar = swap_value * N

        steps.append(CalculationStep(
            step_number=4,
            label="Greeks and parity check",
            formula=(
                r"\text{Delta} = N \sum_i \Delta_i,\quad"
                r"\text{Vega} = N \sum_i \mathcal{V}_i"
            ),
            substitution=(
                f"Delta = {total_delta_dollar:,.0f} (per 1 rate unit).  "
                f"Vega = {total_vega_dollar:,.0f} (per 1% vol).  "
                f"Cap-Floor parity: swap value = {swap_value_dollar:,.2f}"
            ),
            result=round(total_delta_dollar, 0),
            explanation=(
                "Delta is the sensitivity to a parallel shift in all forward rates. "
                "Vega is sensitivity to a 1% (100bp) vol shift. "
                "Cap - Floor = Payer Swap (put-call parity for rates)."
            ),
        ))

        # Premium in bps running
        annuity = sum(dt * math.exp(-r_ois * (i + 2) * dt) for i in range(n_caplets))
        premium_bps = total_price_unit / annuity * 10000 if annuity > 0 else 0

        steps.append(CalculationStep(
            step_number=5,
            label="Premium in running basis points",
            formula=r"\text{bps running} = \frac{\text{upfront}}{A} \times 10000",
            substitution=(
                f"Annuity = {annuity:.6f}.  "
                f"Upfront = {total_price_unit:.8f}.  "
                f"Running = {premium_bps:.2f} bps/year"
            ),
            result=round(premium_bps, 2),
            explanation=(
                "Expressing the upfront cap/floor premium as an equivalent "
                "annual running spread, useful for comparison across tenors."
            ),
        ))

        return SimulatorResult(
            fair_value=round(total_price, 2),
            method="Black-76 (log-normal caplets)",
            greeks={
                "delta": round(total_delta_dollar, 2),
                "vega_1pct": round(total_vega_dollar, 2),
                "premium_bps_running": round(premium_bps, 2),
            },
            calculation_steps=steps,
            diagnostics={
                "n_caplets": n_caplets,
                "price_per_unit_notional": round(total_price_unit, 8),
                "total_premium": round(total_price, 2),
                "premium_bps_upfront": round(total_price_unit * 10000, 2),
                "premium_bps_running": round(premium_bps, 2),
                "swap_value_parity": round(swap_value_dollar, 2),
                "annuity": round(annuity, 6),
                "caplet_details": caplet_details[:5],
            },
        )
