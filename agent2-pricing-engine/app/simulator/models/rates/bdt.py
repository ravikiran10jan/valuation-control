"""Black-Derman-Toy (BDT) lattice model for bond option and callable bond pricing.

BDT (1990) is a log-normal short-rate model calibrated to the current yield curve.
The model builds a recombining binomial tree where the log of the short rate follows
a lattice structure. Each node has an up-move and down-move that preserves the
log-normality of rates, and the tree is calibrated so that zero-coupon bond prices
match the input yield curve.
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


@ModelRegistry.register
class BDTModel(BaseSimulatorModel):

    model_id = "bdt"
    model_name = "Black-Derman-Toy"
    product_type = "Bond Option / Callable Bond"
    asset_class = "rates"

    short_description = (
        "Log-normal short-rate lattice calibrated to the yield curve for "
        "bond options and callable bonds"
    )
    long_description = (
        "The Black-Derman-Toy (1990) model is a single-factor, log-normal short-rate "
        "lattice model. The model is constructed as a recombining binomial tree in which "
        "the short rate r is log-normally distributed at each time step: "
        "r(i,j) = r_i * exp(σ * j * √Δt) where j is the number of up-moves. "
        "Two key properties distinguish BDT: (1) the tree is calibrated to the observed "
        "yield curve so that model zero-coupon bond prices exactly match market prices, "
        "and (2) the volatility structure is calibrated to market cap/swaption volatilities. "
        "The model is widely used for pricing bond options, callable/putable bonds, "
        "and any interest rate derivative whose value depends on the yield curve shape. "
        "Backward induction through the tree gives the price, and sensitivities are "
        "obtained via finite differences."
    )

    when_to_use = [
        "Pricing European and American bond options",
        "Valuing callable or putable bonds with embedded options",
        "When the model must be consistent with the current yield curve",
        "Structured products where the payoff depends on bond prices at future dates",
        "Regulatory / accounting valuations requiring yield-curve-consistent models",
    ]
    when_not_to_use = [
        "When you need stochastic volatility — use Hull-White or SABR",
        "For highly path-dependent products — use Monte Carlo HW or LMM",
        "When negative rates are present — BDT is log-normal and cannot go negative",
        "Very long maturities with many steps (slow, use analytical approximations)",
        "When smile/skew calibration matters — BDT has a single vol parameter",
    ]
    assumptions = [
        "Short rate is log-normally distributed: r cannot go negative",
        "Single-factor model: all rates driven by one Brownian motion",
        "Tree is calibrated to the input zero-coupon yield curve",
        "Constant short-rate volatility σ across all maturities",
        "No market frictions, continuous compounding, no credit risk",
        "Recombining binomial tree: u × d = 1 in log-rate space",
    ]
    limitations = [
        "Log-normality prevents negative rates — not suitable in low/negative rate environments",
        "Single-factor: cannot capture twists or butterfly shifts of the yield curve",
        "Mean reversion is implicit and inconsistent (no explicit θ(t) speed)",
        "Calibration to a full smile requires extensions (BDT + local vol)",
        "O(N²) nodes; fine grids become slow without vectorisation",
        "Discrete tree introduces grid error; need many steps (≥50) for accuracy",
    ]

    formula_latex = (
        r"r(i,j) = r_i \cdot e^{\sigma \cdot j \cdot \sqrt{\Delta t}},\quad"
        r"P(0,T_i) = e^{-y_i T_i},\quad"
        r"V = e^{-r(i,j)\Delta t}\left[\tfrac{1}{2}V_{i+1,j+1} + \tfrac{1}{2}V_{i+1,j}\right]"
    )
    formula_plain = (
        "r(i,j) = r_i * exp(σ * j * √Δt)  [log-normal short rate at node (i,j)]  "
        "P(0,Ti) = exp(-yi*Ti)  [zero-coupon price from input curve]  "
        "Backward induction: V(i,j) = exp(-r(i,j)*Δt) * 0.5*(V(i+1,j+1) + V(i+1,j))  "
        "Calibration: choose r_i so model P(0,Ti) matches input curve exactly"
    )

    # ── Parameters ───────────────────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "face_value", "Face Value", "Bond face / par value",
                "float", 1000.0, 1.0, None, 100.0, unit="$",
            ),
            ParameterSpec(
                "coupon_rate", "Coupon Rate", "Annual coupon rate (decimal)",
                "float", 0.06, 0.0, 0.5, 0.005, unit="decimal",
            ),
            ParameterSpec(
                "maturity", "Bond Maturity (T)", "Time to bond maturity in years",
                "float", 5.0, 0.5, 30.0, 0.5, unit="years",
            ),
            ParameterSpec(
                "strike", "Option Strike", "Strike price of the bond option",
                "float", 980.0, 0.0, None, 10.0, unit="$",
            ),
            ParameterSpec(
                "option_type", "Option Type", "Call or put on the bond",
                "select", "call", options=["call", "put"],
            ),
            ParameterSpec(
                "option_maturity", "Option Expiry (T_opt)", "Time to option expiry in years",
                "float", 2.0, 0.25, 10.0, 0.25, unit="years",
            ),
            ParameterSpec(
                "n_steps", "Tree Steps (N)", "Number of time steps in the BDT tree",
                "int", 50, 5, 200, 5,
            ),
            ParameterSpec(
                "vol_short_rate", "Short-Rate Vol (σ)", "Log-normal short-rate volatility",
                "float", 0.18, 0.001, 2.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "rate_1y", "1Y Spot Rate", "1-year zero rate (continuous)",
                "float", 0.040, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "rate_2y", "2Y Spot Rate", "2-year zero rate (continuous)",
                "float", 0.045, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "rate_5y", "5Y Spot Rate", "5-year zero rate (continuous)",
                "float", 0.050, -0.05, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "rate_10y", "10Y Spot Rate", "10-year zero rate (continuous)",
                "float", 0.055, -0.05, 0.5, 0.001, unit="decimal",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "5Y 6% Bond — 2Y ATM Call": {
                "face_value": 1000.0, "coupon_rate": 0.06, "maturity": 5.0,
                "strike": 980.0, "option_type": "call", "option_maturity": 2.0,
                "n_steps": 50, "vol_short_rate": 0.18,
                "rate_1y": 0.040, "rate_2y": 0.045, "rate_5y": 0.050, "rate_10y": 0.055,
            },
            "10Y 5% Bond — 5Y Put (Callable bond floor)": {
                "face_value": 1000.0, "coupon_rate": 0.05, "maturity": 10.0,
                "strike": 1000.0, "option_type": "put", "option_maturity": 5.0,
                "n_steps": 50, "vol_short_rate": 0.20,
                "rate_1y": 0.035, "rate_2y": 0.040, "rate_5y": 0.045, "rate_10y": 0.050,
            },
            "3Y Zero-Coupon Bond — 1Y Call": {
                "face_value": 1000.0, "coupon_rate": 0.0, "maturity": 3.0,
                "strike": 870.0, "option_type": "call", "option_maturity": 1.0,
                "n_steps": 30, "vol_short_rate": 0.15,
                "rate_1y": 0.045, "rate_2y": 0.047, "rate_5y": 0.050, "rate_10y": 0.054,
            },
            "7Y 4.5% Bond — 3Y ATM Put": {
                "face_value": 1000.0, "coupon_rate": 0.045, "maturity": 7.0,
                "strike": 990.0, "option_type": "put", "option_maturity": 3.0,
                "n_steps": 50, "vol_short_rate": 0.22,
                "rate_1y": 0.042, "rate_2y": 0.046, "rate_5y": 0.051, "rate_10y": 0.056,
            },
        }

    # ── Core helpers ─────────────────────────────────────────────────────────

    def _interp_rate(self, t: float, maturities: list[float],
                     rates: list[float]) -> float:
        """Linear interpolation / flat extrapolation of zero rates."""
        if t <= maturities[0]:
            return rates[0]
        if t >= maturities[-1]:
            return rates[-1]
        for k in range(len(maturities) - 1):
            if maturities[k] <= t <= maturities[k + 1]:
                w = (t - maturities[k]) / (maturities[k + 1] - maturities[k])
                return rates[k] + w * (rates[k + 1] - rates[k])
        return rates[-1]

    def _zero_price(self, t: float, maturities: list[float],
                    rates: list[float]) -> float:
        """Return P(0,t) = exp(-y(t)*t)."""
        if t <= 0:
            return 1.0
        y = self._interp_rate(t, maturities, rates)
        return math.exp(-y * t)

    def _build_bdt_tree(
        self, N: int, dt: float, sigma: float,
        maturities: list[float], rates: list[float]
    ) -> list[list[float]]:
        """
        Calibrate BDT short-rate tree.

        Returns rate_tree[i][j] = short rate at time i*dt, state j (j up-moves).
        We calibrate the base rate r_i at each time step so that the model
        zero-coupon bond price P_model(0, (i+1)*dt) matches P_market(0, (i+1)*dt).

        r(i,j) = r_i * exp(sigma * j * sqrt(dt))
        """
        rate_tree: list[list[float]] = []

        # Time 0 short rate: calibrate 1-step zero price
        P_target_1 = self._zero_price(dt, maturities, rates)
        # P_model(0,dt) = exp(-r0*dt) => r0 = -ln(P) / dt
        r0 = -math.log(P_target_1) / dt if P_target_1 > 0 else 0.05
        rate_tree.append([r0])

        # Iteratively calibrate r_i for each subsequent step
        for i in range(1, N):
            T_target = (i + 1) * dt
            P_target = self._zero_price(T_target, maturities, rates)

            # Binary search for r_i (the base rate at step i)
            lo, hi = 1e-6, 2.0

            for _ in range(80):  # bisection iterations
                mid = 0.5 * (lo + hi)
                # Build rate layer
                layer = [mid * math.exp(sigma * j * math.sqrt(dt))
                         for j in range(i + 1)]
                # Compute model zero price using backward induction
                # Start from nodes at time i with bond maturing at T_target
                bond = [math.exp(-r * dt) for r in layer]  # 1-step bond values
                # Roll back through already-calibrated steps
                for step in range(i - 1, -1, -1):
                    prev_layer = rate_tree[step]
                    bond = [
                        math.exp(-prev_layer[j] * dt) * 0.5 * (bond[j] + bond[j + 1])
                        for j in range(step + 1)
                    ]
                p_model = bond[0]

                if p_model > P_target:
                    lo = mid
                else:
                    hi = mid

            r_i = 0.5 * (lo + hi)
            rate_tree.append([
                r_i * math.exp(sigma * j * math.sqrt(dt)) for j in range(i + 1)
            ])

        return rate_tree

    def _price_bond_on_tree(
        self, rate_tree: list[list[float]], dt: float,
        face: float, coupon: float, bond_steps: int, freq: float
    ) -> list[list[float]]:
        """
        Price a coupon bond on the BDT tree via backward induction.
        Returns value_tree[i][j] for i=0..bond_steps.
        coupon: coupon payment per period (already scaled by dt*freq).
        """
        N = len(rate_tree)
        # Terminal values at bond maturity
        term_step = min(bond_steps, N)

        # Bond value at maturity = face + final coupon
        V: list[float] = [face + coupon] * (term_step + 1)

        # Walk backwards
        for i in range(term_step - 1, -1, -1):
            r_layer = rate_tree[i]
            V_new = []
            for j in range(i + 1):
                continuation = math.exp(-r_layer[j] * dt) * 0.5 * (V[j] + V[j + 1])
                V_new.append(continuation + coupon)  # add coupon at each node
            V = V_new

        return V  # single root value list

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        face = float(params.get("face_value", 1000.0))
        coupon_rate = float(params.get("coupon_rate", 0.06))
        bond_mat = float(params.get("maturity", 5.0))
        strike = float(params.get("strike", 980.0))
        opt_type = params.get("option_type", "call").lower()
        opt_mat = float(params.get("option_maturity", 2.0))
        N = int(params.get("n_steps", 50))
        sigma = float(params.get("vol_short_rate", 0.18))
        r1 = float(params.get("rate_1y", 0.040))
        r2 = float(params.get("rate_2y", 0.045))
        r5 = float(params.get("rate_5y", 0.050))
        r10 = float(params.get("rate_10y", 0.055))

        is_call = opt_type == "call"
        maturities = [1.0, 2.0, 5.0, 10.0]
        rates_curve = [r1, r2, r5, r10]

        # ── Key design: tree covers the FULL bond maturity, not just the option.
        # dt = bond_mat / N so no tree extension is ever needed.
        # opt_step = round(opt_mat / dt) is the expiry column in the tree.
        dt = bond_mat / N
        opt_step = max(1, min(N - 1, int(round(opt_mat / dt))))

        steps_calc: list[CalculationStep] = []

        # ── Step 1: Yield curve & tree grid ──────────────────────────────────
        P_bond = self._zero_price(bond_mat, maturities, rates_curve)
        P_opt  = self._zero_price(opt_mat,  maturities, rates_curve)
        P1     = self._zero_price(1.0,      maturities, rates_curve)

        steps_calc.append(CalculationStep(
            step_number=1,
            label="Yield curve & tree grid setup",
            formula=r"P(0,T) = e^{-y(T) \cdot T},\quad \Delta t = T_{bond}/N",
            substitution=(
                f"Input zero rates: 1Y={r1*100:.2f}%, 2Y={r2*100:.2f}%, "
                f"5Y={r5*100:.2f}%, 10Y={r10*100:.2f}%.  "
                f"P(0,{bond_mat}Y)={P_bond:.5f}, P(0,{opt_mat}Y)={P_opt:.5f}, "
                f"P(0,1Y)={P1:.5f}.  "
                f"Δt = {bond_mat}/{N} = {dt:.5f}Y.  "
                f"Option expiry at tree step {opt_step} "
                f"(= {opt_step*dt:.3f}Y ≈ {opt_mat}Y)"
            ),
            result=round(P_opt, 5),
            explanation=(
                "The BDT tree spans the full bond maturity so that both the bond and "
                "the option can be priced on a single consistent lattice with no "
                "extrapolation beyond the calibrated region. "
                "The option expiry column is the nearest tree step to opt_mat."
            ),
        ))

        # ── Step 2: Calibrate BDT tree over full bond maturity ────────────────
        rate_tree = self._build_bdt_tree(N, dt, sigma, maturities, rates_curve)
        r_root    = rate_tree[0][0]
        r_top_N   = rate_tree[-1][-1]
        r_bot_N   = rate_tree[-1][0]
        r_top_opt = rate_tree[opt_step][-1]
        r_bot_opt = rate_tree[opt_step][0]

        steps_calc.append(CalculationStep(
            step_number=2,
            label="BDT short-rate tree calibration",
            formula=r"r(i,j) = r_i \cdot e^{\sigma j \sqrt{\Delta t}}",
            substitution=(
                f"Root r(0,0) = {r_root*100:.3f}%.  "
                f"At bond maturity (step {N}): "
                f"r_top={r_top_N*100:.3f}%, r_bot={r_bot_N*100:.3f}%.  "
                f"At option expiry (step {opt_step}): "
                f"r_top={r_top_opt*100:.3f}%, r_bot={r_bot_opt*100:.3f}%.  "
                f"Expected spread ratio e^(σ·opt_step·√Δt) = "
                f"{math.exp(sigma*opt_step*math.sqrt(dt)):.4f}, "
                f"actual = {r_top_opt/r_bot_opt:.4f}"
            ),
            result=round(r_root * 100, 4),
            explanation=(
                "Calibration uses bisection at each time step i to find the base "
                "rate r_i such that the model P(0,(i+1)Δt) exactly matches the "
                "market zero-coupon price. All rates remain positive (log-normal). "
                "The tree now covers the full bond maturity — no extension needed."
            ),
        ))

        # ── Step 3: Bond prices at each node at option expiry ─────────────────
        coupon_annual  = face * coupon_rate
        coupon_per_step = coupon_annual * dt   # continuous-coupon flow per Δt

        # Backward induction from bond maturity (step N) to option expiry (step opt_step).
        # V[j] = bond value at state j of the current step.
        V_bond: list[float] = [face + coupon_per_step] * (N + 1)  # terminal payoff

        for i in range(N - 1, opt_step - 1, -1):
            r_layer = rate_tree[i]  # i+1 nodes
            V_new: list[float] = []
            for j in range(i + 1):
                disc_cf = math.exp(-r_layer[j] * dt)
                hold    = disc_cf * 0.5 * (V_bond[j] + V_bond[j + 1])
                V_new.append(hold + coupon_per_step)
            V_bond = V_new
        # V_bond now has (opt_step+1) elements — one per node at option expiry

        bond_at_expiry = V_bond
        n_expiry_nodes = len(bond_at_expiry)
        mid_idx = n_expiry_nodes // 2

        # Analytical flat-curve bond price for sanity check (using forward rates)
        remaining_mat = bond_mat - opt_mat
        fwd_rate_approx = self._interp_rate(
            0.5 * (opt_mat + bond_mat), maturities, rates_curve
        )
        if coupon_rate > 0 and fwd_rate_approx > 0:
            n_periods = int(round(remaining_mat))
            flat_bond = sum(
                coupon_annual * math.exp(-fwd_rate_approx * t)
                for t in [s for s in range(1, n_periods + 1)]
            ) + face * math.exp(-fwd_rate_approx * remaining_mat)
        else:
            flat_bond = face * math.exp(-fwd_rate_approx * remaining_mat)

        steps_calc.append(CalculationStep(
            step_number=3,
            label="Coupon bond values at option expiry nodes",
            formula=(
                r"V_{bond}(i,j) = e^{-r(i,j)\Delta t}"
                r"\left[\tfrac{1}{2}V_{i+1,j+1}+\tfrac{1}{2}V_{i+1,j}\right] + c\Delta t"
            ),
            substitution=(
                f"Rolled back from step {N} (bond maturity) to step {opt_step} "
                f"(option expiry = {opt_step*dt:.2f}Y).  "
                f"Coupon/step = {coupon_per_step:.4f}  "
                f"({coupon_rate*100:.1f}% × {face} × Δt).  "
                f"Bond values at expiry: "
                f"high-rate node = {bond_at_expiry[-1]:.2f}, "
                f"mid node = {bond_at_expiry[mid_idx]:.2f}, "
                f"low-rate node = {bond_at_expiry[0]:.2f}.  "
                f"Flat-curve approx (remaining {remaining_mat:.1f}Y "
                f"@ {fwd_rate_approx*100:.2f}%) = {flat_bond:.2f}"
            ),
            result=round(bond_at_expiry[mid_idx], 4),
            explanation=(
                "Each node's bond value equals the risk-neutral expected discounted "
                "future cash flows (coupons + face) from that node onward. "
                "Low-rate nodes (j=0) yield higher bond prices; high-rate nodes (j=top) "
                "yield lower prices. The mid-node value should be close to the "
                "flat-curve analytical approximation."
            ),
        ))

        # ── Step 4: Option payoffs & roll back to today ───────────────────────
        if is_call:
            payoffs = [max(b - strike, 0.0) for b in bond_at_expiry]
        else:
            payoffs = [max(strike - b, 0.0) for b in bond_at_expiry]

        V_opt: list[float] = list(payoffs)
        for i in range(opt_step - 1, -1, -1):
            r_layer = rate_tree[i]
            V_new_opt: list[float] = []
            for j in range(i + 1):
                V_new_opt.append(
                    math.exp(-r_layer[j] * dt) * 0.5 * (V_opt[j] + V_opt[j + 1])
                )
            V_opt = V_new_opt

        option_price = V_opt[0]
        in_the_money = sum(1 for p in payoffs if p > 0)
        max_payoff   = max(payoffs)
        min_payoff   = min(payoffs)

        steps_calc.append(CalculationStep(
            step_number=4,
            label="Option payoffs & backward induction to today",
            formula=(
                r"\text{Payoff}(j) = \max\!\left(V_{bond}(opt,j)-K,\,0\right)"
                if is_call else
                r"\text{Payoff}(j) = \max\!\left(K - V_{bond}(opt,j),\,0\right)"
            ),
            substitution=(
                f"Strike K = {strike:.2f}.  "
                f"{'Call' if is_call else 'Put'} payoffs: "
                f"max = {max_payoff:.2f}, min = {min_payoff:.2f}.  "
                f"ITM nodes: {in_the_money} / {n_expiry_nodes}.  "
                f"Option price at root = {option_price:.4f}"
            ),
            result=round(option_price, 4),
            explanation=(
                f"The bond {'call' if is_call else 'put'} pays off at option expiry "
                f"(step {opt_step}). Payoffs are discounted back to today via "
                f"risk-neutral backward induction through steps {opt_step-1}→0."
            ),
        ))

        # ── Step 5: Greeks (finite differences on the same tree structure) ────
        bump_sigma  = sigma * 1.02
        tree_v_up   = self._build_bdt_tree(N, dt, bump_sigma, maturities, rates_curve)
        opt_v_up    = self._price_option_on_tree(
            tree_v_up, dt, face, coupon_per_step, N, opt_step, strike, is_call
        )
        vega = (opt_v_up - option_price) / (bump_sigma - sigma)

        rates_up    = [r + 0.0001 for r in rates_curve]
        tree_r_up   = self._build_bdt_tree(N, dt, sigma, maturities, rates_up)
        opt_r_up    = self._price_option_on_tree(
            tree_r_up, dt, face, coupon_per_step, N, opt_step, strike, is_call
        )
        dv01 = (opt_r_up - option_price) / 0.0001   # $ per 1bp parallel shift

        steps_calc.append(CalculationStep(
            step_number=5,
            label="Greeks via finite differences",
            formula=(
                r"\text{Vega} = \frac{V(\sigma{+}\delta\sigma)-V(\sigma)}{\delta\sigma},"
                r"\quad\text{DV01} = \frac{V(r{+}1\text{bp})-V(r)}{1\text{bp}}"
            ),
            substitution=(
                f"σ bump Δσ = {(bump_sigma-sigma)*100:.2f}%.  "
                f"V(σ_up) = {opt_v_up:.4f}.  Vega = {vega:.4f} per unit σ.  "
                f"V(r+1bp) = {opt_r_up:.4f}.  "
                f"DV01 = {dv01:.4f} $ per 1bp parallel rate shift"
            ),
            result=round(vega, 4),
            explanation=(
                "Vega: sensitivity to +1% absolute increase in σ (log-normal short-rate vol). "
                "DV01: sensitivity to +1bp parallel shift in every zero rate on the curve. "
                "Both are computed by full repricing (rebuild + recalibrate the tree)."
            ),
        ))

        # ── Step 6: Straight bond, callable/putable bond decomposition ────────
        straight_price = self._price_straight_bond(
            rate_tree, dt, face, coupon_per_step, N
        )
        callable_price = straight_price - (option_price if is_call  else 0.0)
        putable_price  = straight_price + (option_price if not is_call else 0.0)

        steps_calc.append(CalculationStep(
            step_number=6,
            label="Straight bond, callable bond & OAS decomposition",
            formula=(
                r"V_{callable} = V_{straight} - C_{call},\quad"
                r"V_{putable}  = V_{straight} + C_{put}"
            ),
            substitution=(
                f"Straight bond (full BDT tree, t=0) = {straight_price:.4f}.  "
                f"{'Call' if is_call else 'Put'} option = {option_price:.4f}.  "
                f"Callable bond = {callable_price:.4f}  "
                f"(issuer retains call; bond is worth less to investor).  "
                f"Putable bond = {putable_price:.4f}."
            ),
            result=round(straight_price, 4),
            explanation=(
                "The straight bond price is the PV of all coupons + face discounted "
                "through the BDT tree. Callable bond = straight – call (issuer holds "
                "the embedded call). Putable bond = straight + put (investor holds "
                "the put). OAS is the spread added to all tree rates that equates "
                "model callable price to the observed market price."
            ),
        ))

        return SimulatorResult(
            fair_value=round(option_price, 4),
            method=f"BDT Lattice ({N} steps over {bond_mat}Y, log-normal rates)",
            greeks={
                "vega": round(vega, 4),
                "dv01": round(dv01, 4),
            },
            calculation_steps=steps_calc,
            diagnostics={
                "n_steps": N,
                "dt": round(dt, 6),
                "opt_step": opt_step,
                "root_short_rate_pct": round(r_root * 100, 4),
                "sigma_pct": round(sigma * 100, 2),
                "option_price": round(option_price, 4),
                "straight_bond_price": round(straight_price, 4),
                "callable_bond_price": round(callable_price, 4),
                "putable_bond_price": round(putable_price, 4),
                "itm_nodes_at_expiry": in_the_money,
                "total_nodes_at_expiry": n_expiry_nodes,
                "bond_at_expiry_low_rate_node": round(bond_at_expiry[0], 2),
                "bond_at_expiry_mid_node": round(bond_at_expiry[mid_idx], 2),
                "bond_at_expiry_high_rate_node": round(bond_at_expiry[-1], 2),
                "flat_curve_bond_approx": round(flat_bond, 2),
            },
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _price_option_on_tree(
        self,
        rate_tree: list[list[float]],
        dt: float,
        face: float,
        coupon_per_step: float,
        bond_steps: int,   # = N (tree covers full bond maturity)
        opt_step: int,
        strike: float,
        is_call: bool,
    ) -> float:
        """Full reprice of bond option on an existing rate tree (for Greeks)."""
        V_bond: list[float] = [face + coupon_per_step] * (bond_steps + 1)
        for i in range(bond_steps - 1, opt_step - 1, -1):
            r_layer = rate_tree[i]
            V_new: list[float] = []
            for j in range(i + 1):
                V_new.append(
                    math.exp(-r_layer[j] * dt) * 0.5 * (V_bond[j] + V_bond[j + 1])
                    + coupon_per_step
                )
            V_bond = V_new

        if is_call:
            payoffs = [max(b - strike, 0.0) for b in V_bond]
        else:
            payoffs = [max(strike - b, 0.0) for b in V_bond]

        V_opt: list[float] = list(payoffs)
        for i in range(opt_step - 1, -1, -1):
            r_layer = rate_tree[i]
            V_new_opt: list[float] = []
            for j in range(i + 1):
                V_new_opt.append(
                    math.exp(-r_layer[j] * dt) * 0.5 * (V_opt[j] + V_opt[j + 1])
                )
            V_opt = V_new_opt

        return V_opt[0]

    def _price_straight_bond(
        self,
        rate_tree: list[list[float]],
        dt: float,
        face: float,
        coupon_per_step: float,
        bond_steps: int,
    ) -> float:
        """Price the straight (option-free) coupon bond back to today."""
        V: list[float] = [face + coupon_per_step] * (bond_steps + 1)
        for i in range(bond_steps - 1, -1, -1):
            r_layer = rate_tree[i]
            V_new: list[float] = []
            for j in range(i + 1):
                V_new.append(
                    math.exp(-r_layer[j] * dt) * 0.5 * (V[j] + V[j + 1])
                    + coupon_per_step
                )
            V = V_new
        return V[0]
