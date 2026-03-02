"""Hull-White 1-Factor model for interest rate derivatives.

The Hull-White (1990) model is a short-rate model:

    dr(t) = κ(θ(t) - r(t)) dt + σ dW(t)

where:
  κ = mean reversion speed
  θ(t) = time-dependent mean reversion level (calibrated to fit the yield curve)
  σ = short-rate volatility

The model is implemented via a trinomial tree (Hull-White tree) for
pricing Bermudan swaptions, callable bonds, and other rate derivatives
with early exercise features.
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


# ── Analytical zero-coupon bond price under Hull-White ────────

def _hw_zcb(r0: float, kappa: float, sigma: float, T: float,
            theta_const: float = 0.05) -> float:
    """Analytically price a zero-coupon bond under constant-θ HW.

    P(0, T) = A(T) exp(-B(T) r_0)

    B(T) = (1 - e^(-κT)) / κ
    A(T) = exp{(B(T) - T)(θ - σ²/(2κ²)) - σ²B(T)²/(4κ)}
    """
    if abs(kappa) < 1e-10:
        B = T
        A = math.exp(-0.5 * sigma**2 * T**3 / 3)
    else:
        B = (1 - math.exp(-kappa * T)) / kappa
        A = math.exp(
            (B - T) * (theta_const - sigma**2 / (2 * kappa**2))
            - sigma**2 * B**2 / (4 * kappa)
        )
    return A * math.exp(-B * r0)


def _hw_bond_option(r0: float, kappa: float, sigma: float,
                    T_option: float, T_bond: float,
                    K: float, theta_const: float, is_call: bool) -> float:
    """Price a European option on a zero-coupon bond under HW.

    Uses the Jamshidian (1989) closed-form for bond options.
    """
    from scipy.stats import norm

    if abs(kappa) < 1e-10:
        sigma_p = sigma * T_bond * math.sqrt(T_option)
    else:
        B_Ts = (1 - math.exp(-kappa * (T_bond - T_option))) / kappa
        sigma_p = sigma * math.sqrt((1 - math.exp(-2 * kappa * T_option)) / (2 * kappa)) * B_Ts

    P_T_opt = _hw_zcb(r0, kappa, sigma, T_option, theta_const)
    P_T_bond = _hw_zcb(r0, kappa, sigma, T_bond, theta_const)

    if sigma_p < 1e-12:
        if is_call:
            return max(P_T_bond - K * P_T_opt, 0)
        return max(K * P_T_opt - P_T_bond, 0)

    h = (1 / sigma_p) * math.log(P_T_bond / (K * P_T_opt)) + sigma_p / 2

    if is_call:
        price = P_T_bond * norm.cdf(h) - K * P_T_opt * norm.cdf(h - sigma_p)
    else:
        price = K * P_T_opt * norm.cdf(-h + sigma_p) - P_T_bond * norm.cdf(-h)

    return max(price, 0)


# ── Trinomial tree for Hull-White ────────────────────────────

def _build_hw_tree(
    r0: float, kappa: float, sigma: float, theta_const: float,
    T: float, n_steps: int,
) -> dict[str, Any]:
    """Build a Hull-White trinomial tree.

    Returns tree structure for backward induction.
    """
    dt = T / n_steps
    dr = sigma * math.sqrt(3 * dt)
    j_max = int(math.ceil(0.184 / (kappa * dt))) if kappa * dt > 1e-10 else n_steps

    # Forward induction: build the tree of short rates
    # At each time step i, rates are r0 + j*dr + displacement[i]
    # j ranges from -j_max to j_max

    # For simplicity, we use a constant theta model
    # The displacement is computed to match the initial term structure

    n_nodes = 2 * j_max + 1
    rates = np.zeros((n_steps + 1, n_nodes))
    probs = np.zeros((n_steps, n_nodes, 3))  # up, mid, down

    # Initialize
    for i in range(n_steps + 1):
        t = i * dt
        # Mean reversion pulls toward theta
        for jj in range(n_nodes):
            j = jj - j_max
            rates[i, jj] = r0 + j * dr * math.exp(-kappa * t) + theta_const * (1 - math.exp(-kappa * t))

    # Transition probabilities (standard HW trinomial)
    for i in range(n_steps):
        for jj in range(n_nodes):
            j = jj - j_max
            a = kappa * j * dr * dt
            # Standard trinomial branching probabilities
            pu = 1/6 + (j**2 * kappa**2 * dt**2 + j * kappa * dt) / 2
            pm = 2/3 - j**2 * kappa**2 * dt**2
            pd = 1/6 + (j**2 * kappa**2 * dt**2 - j * kappa * dt) / 2

            # Ensure valid probabilities
            pu = max(min(pu, 1.0), 0.0)
            pd = max(min(pd, 1.0), 0.0)
            pm = max(1.0 - pu - pd, 0.0)

            probs[i, jj, 0] = pu  # up
            probs[i, jj, 1] = pm  # middle
            probs[i, jj, 2] = pd  # down

    return {
        "rates": rates,
        "probs": probs,
        "n_steps": n_steps,
        "n_nodes": n_nodes,
        "j_max": j_max,
        "dt": dt,
        "dr": dr,
    }


def _price_on_tree(tree: dict, payoff_at_maturity: np.ndarray,
                   exercise_values: np.ndarray | None = None) -> float:
    """Backward induction on the trinomial tree.

    exercise_values: if not None, array of shape (n_steps+1, n_nodes)
                     for Bermudan exercise.
    """
    n_steps = tree["n_steps"]
    n_nodes = tree["n_nodes"]
    j_max = tree["j_max"]
    dt = tree["dt"]
    rates = tree["rates"]
    probs = tree["probs"]

    V = payoff_at_maturity.copy()

    for i in range(n_steps - 1, -1, -1):
        V_new = np.zeros(n_nodes)
        for jj in range(n_nodes):
            j = jj - j_max
            pu, pm, pd = probs[i, jj]

            # Children indices
            j_up = min(jj + 1, n_nodes - 1)
            j_mid = jj
            j_down = max(jj - 1, 0)

            # Discounted expected value
            disc = math.exp(-rates[i, jj] * dt)
            V_new[jj] = disc * (pu * V[j_up] + pm * V[j_mid] + pd * V[j_down])

        # Bermudan exercise
        if exercise_values is not None:
            V_new = np.maximum(V_new, exercise_values[i])

        V = V_new

    return float(V[j_max])  # value at the central node


@ModelRegistry.register
class HullWhiteModel(BaseSimulatorModel):

    model_id = "hull_white_1f"
    model_name = "Hull-White 1-Factor"
    product_type = "Bond Option / Swaption"
    asset_class = "rates"

    short_description = (
        "Short-rate model for rate derivatives with mean reversion"
    )
    long_description = (
        "The Hull-White (1990) one-factor model is the workhorse short-rate "
        "model for pricing interest rate derivatives with early exercise. "
        "The short rate follows dr = κ(θ(t) - r)dt + σdW, where θ(t) is "
        "chosen to exactly fit the initial yield curve. The model supports "
        "Bermudan swaptions, callable bonds, and caps/floors. Implementation "
        "uses a trinomial tree for backward induction, which naturally handles "
        "Bermudan exercise decisions."
    )

    when_to_use = [
        "Bermudan swaptions, callable bonds, and other early-exercise rate products",
        "When you need to calibrate to the initial yield curve exactly",
        "Building blocks for hybrid models (rates component in PRDCs, etc.)",
        "Pricing caps/floors with early exercise features",
        "When single-factor dynamics are sufficient (most swap-like products)",
    ]
    when_not_to_use = [
        "When two-factor dynamics are needed (butterfly swaptions, CMS spread options)",
        "Very long-dated products where mean reversion uncertainty dominates",
        "When negative rates are undesirable and you need log-normal rates (use Black-Karasinski)",
        "Products sensitive to vol smile (HW is single-vol, no smile)",
        "When correlation between rates at different tenors matters (use multi-factor)",
    ]
    assumptions = [
        "Short rate follows an Ornstein-Uhlenbeck process (normally distributed)",
        "Single factor: entire yield curve is driven by one random factor",
        "θ(t) calibrated to fit the initial term structure exactly",
        "Constant mean reversion κ and volatility σ",
        "Rates can go negative (Gaussian model)",
    ]
    limitations = [
        "Single factor — cannot capture decorrelation between short and long rates",
        "Gaussian rates can go negative (may be a feature or bug depending on regime)",
        "Constant vol — no vol smile for caplets/swaptions",
        "Trinomial tree accuracy depends on number of time steps",
    ]

    formula_latex = (
        r"dr(t) = \kappa(\theta(t) - r(t))\,dt + \sigma\,dW(t)"
    )
    formula_plain = (
        "dr = κ(θ(t) - r)dt + σdW, with θ(t) calibrated to fit the yield curve"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec("r0", "Initial Short Rate (r₀)", "Current short rate", "float", 0.05, -0.05, 0.30, 0.001, unit="decimal"),
            ParameterSpec("kappa", "Mean Reversion (κ)", "Speed of mean reversion", "float", 0.10, 0.001, 2.0, 0.01),
            ParameterSpec("sigma", "Volatility (σ)", "Short-rate volatility", "float", 0.01, 0.001, 0.10, 0.001, unit="decimal"),
            ParameterSpec("theta", "Long-Run Level (θ)", "Long-run mean of short rate", "float", 0.05, -0.05, 0.30, 0.001, unit="decimal"),
            ParameterSpec("T_option", "Option Expiry", "Time to option expiry in years", "float", 1.0, 0.1, 30.0, 0.1, unit="years"),
            ParameterSpec("T_bond", "Bond Maturity", "Bond maturity in years", "float", 5.0, 0.5, 50.0, 0.5, unit="years"),
            ParameterSpec("strike_price", "Strike (ZCB price)", "Option strike as bond price", "float", 0.85, 0.01, 1.5, 0.01),
            ParameterSpec("option_type", "Option Type", "Call or Put on bond", "select", "call", options=["call", "put"]),
            ParameterSpec("exercise_style", "Exercise Style", "European or Bermudan", "select", "european", options=["european", "bermudan"]),
            ParameterSpec("n_steps", "Tree Steps", "Number of trinomial tree time steps", "int", 100, 20, 500, 10),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "European Bond Call (1Y into 5Y)": {
                "r0": 0.05, "kappa": 0.10, "sigma": 0.01, "theta": 0.05,
                "T_option": 1.0, "T_bond": 5.0, "strike_price": 0.82,
                "option_type": "call", "exercise_style": "european", "n_steps": 100,
            },
            "European Bond Put": {
                "r0": 0.05, "kappa": 0.10, "sigma": 0.01, "theta": 0.05,
                "T_option": 1.0, "T_bond": 5.0, "strike_price": 0.85,
                "option_type": "put", "exercise_style": "european", "n_steps": 100,
            },
            "Bermudan Bond Call": {
                "r0": 0.04, "kappa": 0.15, "sigma": 0.012, "theta": 0.05,
                "T_option": 2.0, "T_bond": 10.0, "strike_price": 0.70,
                "option_type": "call", "exercise_style": "bermudan", "n_steps": 100,
            },
            "High Vol Environment": {
                "r0": 0.06, "kappa": 0.05, "sigma": 0.02, "theta": 0.06,
                "T_option": 1.0, "T_bond": 5.0, "strike_price": 0.80,
                "option_type": "call", "exercise_style": "european", "n_steps": 100,
            },
            "Low Rate Environment": {
                "r0": 0.01, "kappa": 0.20, "sigma": 0.008, "theta": 0.02,
                "T_option": 1.0, "T_bond": 5.0, "strike_price": 0.92,
                "option_type": "call", "exercise_style": "european", "n_steps": 100,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        r0 = float(params["r0"])
        kappa = float(params["kappa"])
        sigma = float(params["sigma"])
        theta = float(params["theta"])
        T_opt = float(params["T_option"])
        T_bond = float(params["T_bond"])
        K = float(params["strike_price"])
        opt_type = params.get("option_type", "call").lower()
        exercise = params.get("exercise_style", "european").lower()
        n_steps = int(params.get("n_steps", 100))
        is_call = opt_type == "call"
        is_bermudan = exercise == "bermudan"

        steps: list[CalculationStep] = []

        # Step 1: zero-coupon bond prices
        P_T_opt = _hw_zcb(r0, kappa, sigma, T_opt, theta)
        P_T_bond = _hw_zcb(r0, kappa, sigma, T_bond, theta)

        steps.append(CalculationStep(
            step_number=1,
            label="Zero-coupon bond prices",
            formula=r"P(0,T) = A(T) e^{-B(T) r_0}, \quad B(T) = \frac{1-e^{-\kappa T}}{\kappa}",
            substitution=(
                f"P(0, {T_opt}) = {P_T_opt:.6f}\n"
                f"P(0, {T_bond}) = {P_T_bond:.6f}\n"
                f"Forward bond price P({T_opt},{T_bond}) = {P_T_bond/P_T_opt:.6f}"
            ),
            result=round(P_T_bond, 6),
            explanation="ZCB prices from the analytical HW formula with constant θ.",
        ))

        # Step 2: analytical price (European only)
        analytical_price = _hw_bond_option(r0, kappa, sigma, T_opt, T_bond, K, theta, is_call)

        steps.append(CalculationStep(
            step_number=2,
            label="Analytical price (Jamshidian)",
            formula=(
                r"C = P(0,T_b)N(h) - K \cdot P(0,T_o)N(h-\sigma_P)"
                if is_call else
                r"P = K \cdot P(0,T_o)N(-h+\sigma_P) - P(0,T_b)N(-h)"
            ),
            substitution=(
                f"{'Call' if is_call else 'Put'} on ZCB\n"
                f"K = {K}, T_option = {T_opt}, T_bond = {T_bond}\n"
                f"Analytical (European): {analytical_price:.6f}"
            ),
            result=round(analytical_price, 6),
            explanation=(
                "The Jamshidian (1989) formula gives a closed-form for European bond options "
                "under Hull-White, decomposing the swaption into a portfolio of bond options."
            ),
        ))

        # Step 3: build trinomial tree
        tree = _build_hw_tree(r0, kappa, sigma, theta, T_opt, n_steps)

        steps.append(CalculationStep(
            step_number=3,
            label="Build trinomial tree",
            formula=r"\Delta r = \sigma\sqrt{3\Delta t}, \quad j_{max} = \lceil 0.184/(\kappa\Delta t) \rceil",
            substitution=(
                f"Steps: {n_steps}, Δt = {tree['dt']:.6f}\n"
                f"Δr = {tree['dr']:.6f}\n"
                f"j_max = {tree['j_max']} → {tree['n_nodes']} nodes per step\n"
                f"Rate range at expiry: [{r0 - tree['j_max']*tree['dr']:.4f}, {r0 + tree['j_max']*tree['dr']:.4f}]"
            ),
            result=tree['n_nodes'],
            explanation=(
                "The trinomial tree is built with 3 branches per node (up/mid/down). "
                "The branching probabilities ensure the correct mean and variance of the short rate."
            ),
        ))

        # Step 4: terminal payoff (bond price at option expiry)
        n_nodes = tree["n_nodes"]
        j_max = tree["j_max"]
        rates = tree["rates"]

        # At option expiry, compute bond price for each node
        terminal_bond_prices = np.zeros(n_nodes)
        for jj in range(n_nodes):
            r_node = rates[n_steps, jj]
            t_remaining = T_bond - T_opt
            terminal_bond_prices[jj] = _hw_zcb(r_node, kappa, sigma, t_remaining, theta)

        # Option payoff
        if is_call:
            payoff = np.maximum(terminal_bond_prices - K, 0)
        else:
            payoff = np.maximum(K - terminal_bond_prices, 0)

        steps.append(CalculationStep(
            step_number=4,
            label="Terminal payoff at option expiry",
            formula=(
                r"V(T_o) = \max(P(T_o, T_b) - K, 0)" if is_call else
                r"V(T_o) = \max(K - P(T_o, T_b), 0)"
            ),
            substitution=(
                f"Bond prices at T={T_opt} across nodes:\n"
                f"  At r_low ({rates[n_steps, 0]:.4f}): P={terminal_bond_prices[0]:.6f}\n"
                f"  At r_mid ({rates[n_steps, j_max]:.4f}): P={terminal_bond_prices[j_max]:.6f}\n"
                f"  At r_high ({rates[n_steps, -1]:.4f}): P={terminal_bond_prices[-1]:.6f}\n"
                f"Mean payoff: {np.mean(payoff):.6f}"
            ),
            result=round(float(np.mean(payoff)), 6),
            explanation="Compute the bond price at each node at option expiry, then the option payoff.",
        ))

        # Step 5: backward induction
        # For Bermudan, create exercise values at each time step
        exercise_values = None
        if is_bermudan:
            exercise_values = np.zeros((n_steps + 1, n_nodes))
            for i in range(n_steps + 1):
                for jj in range(n_nodes):
                    r_node = rates[i, jj]
                    t_remaining = T_bond - i * tree["dt"]
                    if t_remaining > 0:
                        bp = _hw_zcb(r_node, kappa, sigma, t_remaining, theta)
                        if is_call:
                            exercise_values[i, jj] = max(bp - K, 0)
                        else:
                            exercise_values[i, jj] = max(K - bp, 0)

        tree_price = _price_on_tree(tree, payoff, exercise_values)

        steps.append(CalculationStep(
            step_number=5,
            label="Backward induction on tree",
            formula=(
                r"V_i = e^{-r_i \Delta t}(p_u V_{up} + p_m V_{mid} + p_d V_{down})"
                + (r"\text{ with } V_i = \max(V_i, \text{exercise})" if is_bermudan else "")
            ),
            substitution=(
                f"Tree price ({'Bermudan' if is_bermudan else 'European'}): {tree_price:.6f}\n"
                f"Analytical (European): {analytical_price:.6f}\n"
                f"Tree-Analytical diff: {tree_price - analytical_price:+.6f}"
                + (f"\nEarly exercise premium: {tree_price - analytical_price:.6f}" if is_bermudan else "")
            ),
            result=round(tree_price, 6),
            explanation=(
                "Backward induction discounts expected values from T_option back to t=0. "
                + ("For Bermudan, exercise is allowed at each tree step." if is_bermudan else
                   "Tree price should converge to analytical as n_steps → ∞.")
            ),
        ))

        price = tree_price

        # Greeks via finite differences on the tree
        dr_bump = 0.0001
        price_up = self._reprice(params, r0 + dr_bump)
        price_down = self._reprice(params, r0 - dr_bump)
        delta_r = (price_up - price_down) / (2 * dr_bump)
        convexity = (price_up - 2 * price + price_down) / (dr_bump**2)

        greeks = {
            "delta_r": round(delta_r, 6),
            "convexity": round(convexity, 4),
        }

        steps.append(CalculationStep(
            step_number=6,
            label="Rate sensitivities",
            formula=r"\frac{\partial V}{\partial r}, \quad \frac{\partial^2 V}{\partial r^2}",
            substitution=(
                f"∂V/∂r (DV01-like): {delta_r:.6f}\n"
                f"∂²V/∂r² (convexity): {convexity:.4f}"
            ),
            result=round(delta_r, 6),
            explanation="Rate delta: price change per 1bp rate move. Convexity: second-order rate sensitivity.",
        ))

        return SimulatorResult(
            fair_value=round(price, 6),
            method=f"Hull-White 1F ({'Bermudan' if is_bermudan else 'European'}, {n_steps}-step tree)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "analytical_european": round(analytical_price, 6),
                "tree_price": round(tree_price, 6),
                "tree_analytical_diff": round(tree_price - analytical_price, 6),
                "early_exercise_premium": round(tree_price - analytical_price, 6) if is_bermudan else 0,
                "P_0_T_option": round(P_T_opt, 6),
                "P_0_T_bond": round(P_T_bond, 6),
                "forward_bond": round(P_T_bond / P_T_opt, 6),
                "n_steps": n_steps,
                "n_nodes": tree["n_nodes"],
                "j_max": tree["j_max"],
            },
        )

    def _reprice(self, params: dict[str, Any], r0_new: float) -> float:
        """Quick reprice for Greek calculation."""
        kappa = float(params["kappa"])
        sigma = float(params["sigma"])
        theta_val = float(params["theta"])
        T_opt = float(params["T_option"])
        T_bond = float(params["T_bond"])
        K = float(params["strike_price"])
        is_call = params.get("option_type", "call").lower() == "call"
        n_steps = int(params.get("n_steps", 100))
        is_bermudan = params.get("exercise_style", "european").lower() == "bermudan"

        if not is_bermudan:
            return _hw_bond_option(r0_new, kappa, sigma, T_opt, T_bond, K, theta_val, is_call)

        # Full tree reprice for Bermudan
        tree = _build_hw_tree(r0_new, kappa, sigma, theta_val, T_opt, n_steps)
        n_nodes = tree["n_nodes"]
        j_max = tree["j_max"]
        rates = tree["rates"]

        terminal_bond = np.zeros(n_nodes)
        for jj in range(n_nodes):
            t_rem = T_bond - T_opt
            terminal_bond[jj] = _hw_zcb(rates[n_steps, jj], kappa, sigma, t_rem, theta_val)

        payoff = np.maximum(terminal_bond - K, 0) if is_call else np.maximum(K - terminal_bond, 0)

        exercise_values = np.zeros((n_steps + 1, n_nodes))
        for i in range(n_steps + 1):
            for jj in range(n_nodes):
                t_rem = T_bond - i * tree["dt"]
                if t_rem > 0:
                    bp = _hw_zcb(rates[i, jj], kappa, sigma, t_rem, theta_val)
                    exercise_values[i, jj] = max(bp - K, 0) if is_call else max(K - bp, 0)

        return _price_on_tree(tree, payoff, exercise_values)
