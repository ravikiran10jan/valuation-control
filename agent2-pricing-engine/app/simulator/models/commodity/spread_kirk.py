"""Kirk's approximation for commodity spread options.

A spread option pays max(F1 - F2 - K, 0) (call) or max(K - (F1 - F2), 0) (put).
Common examples: crack spread (refined product vs crude), spark spread
(electricity vs natural gas), crush spread (soy meal/oil vs soybeans), and
calendar spreads on the same commodity.

Kirk (1995) provides a highly accurate closed-form approximation by transforming
the two-asset spread problem into a single-asset Black-76 problem with an
adjusted futures price and effective volatility.
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
    """Standard normal CDF using math.erfc."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _norm_pdf(x: float) -> float:
    """Standard normal PDF."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


@ModelRegistry.register
class KirkSpreadOptionModel(BaseSimulatorModel):

    model_id = "spread_kirk"
    model_name = "Kirk Spread Option"
    product_type = "Spread Option (Crack/Spark)"
    asset_class = "commodity"

    short_description = (
        "Kirk's closed-form approximation for commodity spread options "
        "(crack, spark, crush, calendar)"
    )
    long_description = (
        "A commodity spread option pays max(F1 - F2 - K, 0) where F1 and F2 are "
        "two correlated futures prices. Kirk (1995) approximates this by treating "
        "F2 + K as a single 'adjusted futures price' F2* = F2 + K*exp(-rT), and "
        "computing an effective spread volatility σ_eff via the formula: "
        "σ_eff² ≈ σ1² - 2ρ·(F2*/(F1+F2*))·σ1·σ2 + (F2*/(F1+F2*))²·σ2². "
        "The spread option is then treated as a Black-76 call on an 'effective futures' "
        "F_eff = F1/(F2 + K·exp(-rT)) with volatility σ_eff. "
        "Kirk's approximation is extremely accurate for moderate correlations (ρ > 0.5) "
        "and small strikes (near-zero K), which are the most common practical cases. "
        "It is the industry standard for crack and spark spread options."
    )

    when_to_use = [
        "Crack spread options: 3-2-1 (crude to gasoline/diesel), 2-1-1",
        "Spark spread options: electricity vs natural gas futures",
        "Crush spread options: soybean complex (beans vs meal/oil)",
        "Calendar spread options on the same commodity (different tenors)",
        "When strike K is small relative to F1 and F2 (Kirk is very accurate)",
        "Fast approximate Greeks for spread option books",
    ]
    when_not_to_use = [
        "Large strikes K relative to F2 — Kirk approximation degrades",
        "When exact pricing matters and K >> F2: use Margrabe (K=0) or Monte Carlo",
        "American-style spread options — use LSM Monte Carlo",
        "Three-leg or complex spread baskets — use Monte Carlo",
        "When the correlation ρ is unstable or near ±1",
    ]
    assumptions = [
        "Both F1 and F2 follow log-normal GBM with constant vols and correlation",
        "Instantaneous correlation ρ between log(F1) and log(F2) is constant",
        "European exercise only — no early exercise",
        "Interest rates are deterministic (single discount rate r)",
        "Kirk approximation is exact in the limit K→0 (reduces to Margrabe's formula)",
        "No transaction costs, no credit risk",
    ]
    limitations = [
        "Approximation: small error when strike K is large relative to F2 price",
        "Log-normal: neither F1 nor F2 can go negative (problems for electricity spreads)",
        "Single constant correlation ρ — does not capture correlation smile",
        "Constant vols: misses term structure and skew effects",
        "Kirk's approximation slightly overprices spread calls for large K",
    ]

    formula_latex = (
        r"F_2^* = F_2 + K e^{-rT},\quad"
        r"\sigma_{\text{eff}} = \sqrt{\sigma_1^2 - 2\rho "
        r"\tfrac{F_2^*}{F_1+F_2^*}\sigma_1\sigma_2 + "
        r"\left(\tfrac{F_2^*}{F_1+F_2^*}\right)^2\!\sigma_2^2},\quad"
        r"C = e^{-rT}\left[(F_1+F_2^*)N(d_1) - F_2^* N(d_2)\right]"
    )
    formula_plain = (
        "F2* = F2 + K*exp(-rT)  [adjusted denominator futures]  "
        "σ_eff² = σ1² - 2ρ*(F2*/(F1+F2*))*σ1*σ2 + (F2*/(F1+F2*))²*σ2²  "
        "d1 = [ln(F1/F2*) + 0.5*σ_eff²*T] / (σ_eff*√T)  "
        "d2 = d1 - σ_eff*√T  "
        "C = exp(-rT)*[F1*N(d1) - F2**N(d2)]"
    )

    # ── Parameters ───────────────────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "f1", "Futures Price 1 (F1)",
                "First (long) futures price — the commodity being bought",
                "float", 90.0, 0.01, None, 0.01, unit="$/unit",
            ),
            ParameterSpec(
                "f2", "Futures Price 2 (F2)",
                "Second (short) futures price — the commodity being sold",
                "float", 80.0, 0.01, None, 0.01, unit="$/unit",
            ),
            ParameterSpec(
                "strike", "Strike Spread (K)",
                "Minimum spread required for the option to pay off",
                "float", 5.0, 0.0, None, 0.5, unit="$/unit",
            ),
            ParameterSpec(
                "maturity", "Time to Expiry (T)",
                "Option time to expiration in years",
                "float", 0.5, 0.001, 5.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "vol1", "Volatility F1 (σ1)",
                "Annualized Black-76 implied volatility of F1",
                "float", 0.35, 0.001, 5.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "vol2", "Volatility F2 (σ2)",
                "Annualized Black-76 implied volatility of F2",
                "float", 0.25, 0.001, 5.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "rho", "Correlation (ρ)",
                "Instantaneous correlation between ln(F1) and ln(F2)",
                "float", 0.80, -1.0, 1.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate (r)",
                "Continuous risk-free discount rate",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "option_type", "Option Type",
                "Call: max(F1-F2-K,0) | Put: max(K-(F1-F2),0)",
                "select", "call", options=["call", "put"],
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "3-2-1 Crack Spread Call (Crude→Gasoline/Diesel, 6M)": {
                "f1": 252.0, "f2": 240.0, "strike": 8.0, "maturity": 0.5,
                "vol1": 0.30, "vol2": 0.28, "rho": 0.85, "r": 0.05,
                "option_type": "call",
            },
            "Spark Spread Call (Power vs Nat Gas, 1Y)": {
                "f1": 65.0, "f2": 42.0, "strike": 15.0, "maturity": 1.0,
                "vol1": 0.45, "vol2": 0.55, "rho": 0.60, "r": 0.05,
                "option_type": "call",
            },
            "Crush Spread Put (Soybeans vs Meal+Oil, 3M)": {
                "f1": 450.0, "f2": 440.0, "strike": 0.0, "maturity": 0.25,
                "vol1": 0.22, "vol2": 0.20, "rho": 0.92, "r": 0.05,
                "option_type": "put",
            },
            "Calendar Spread Call (WTI M1 vs M6, 3M)": {
                "f1": 82.0, "f2": 80.0, "strike": 0.0, "maturity": 0.25,
                "vol1": 0.35, "vol2": 0.30, "rho": 0.97, "r": 0.05,
                "option_type": "call",
            },
        }

    # ── Calculation ──────────────────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        F1 = float(params["f1"])
        F2 = float(params["f2"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma1 = float(params["vol1"])
        sigma2 = float(params["vol2"])
        rho = float(params["rho"])
        r = float(params["r"])
        opt_type = params.get("option_type", "call").lower()
        is_call = opt_type == "call"

        steps: list[CalculationStep] = []
        df = math.exp(-r * T)
        sqrt_T = math.sqrt(T)

        # ── Step 1: Kirk transformation ───────────────────────────────────────
        # F2* = F2 + K*exp(-rT)  [adjusted strike-inclusive denominator]
        F2_star = F2 + K * df

        # Weight w = F2* / (F1 + F2*)  used in vol blending
        w = F2_star / (F1 + F2_star)

        steps.append(CalculationStep(
            step_number=1,
            label="Kirk transformation: adjusted futures F2*",
            formula=r"F_2^* = F_2 + K e^{-rT},\quad w = \frac{F_2^*}{F_1 + F_2^*}",
            substitution=(
                f"F1={F1}, F2={F2}, K={K}, T={T}Y, r={r}.  "
                f"DF = e^{{-rT}} = {df:.6f}.  "
                f"K*DF = {K*df:.4f}.  "
                f"F2* = {F2} + {K*df:.4f} = {F2_star:.4f}.  "
                f"w = {F2_star:.4f}/({F1}+{F2_star:.4f}) = {w:.6f}"
            ),
            result=round(F2_star, 4),
            explanation=(
                "Kirk's key insight: absorb the discounted strike into F2. "
                "The weight w measures how much F2 (plus strike) contributes to "
                "the total 'denominator' of the spread. When K=0, this reduces "
                "exactly to Margrabe's exchange option formula."
            ),
        ))

        # ── Step 2: Effective spread volatility ───────────────────────────────
        var_eff = (
            sigma1 ** 2
            - 2.0 * rho * w * sigma1 * sigma2
            + (w * sigma2) ** 2
        )
        sigma_eff = math.sqrt(max(var_eff, 1e-10))

        steps.append(CalculationStep(
            step_number=2,
            label="Effective spread volatility σ_eff",
            formula=(
                r"\sigma_{\text{eff}}^2 = \sigma_1^2 "
                r"- 2\rho w \sigma_1\sigma_2 + (w\sigma_2)^2"
            ),
            substitution=(
                f"σ1={sigma1}, σ2={sigma2}, ρ={rho}, w={w:.6f}.  "
                f"σ1² = {sigma1**2:.6f},  "
                f"2ρ·w·σ1·σ2 = {2*rho*w*sigma1*sigma2:.6f},  "
                f"(w·σ2)² = {(w*sigma2)**2:.6f}.  "
                f"σ_eff² = {var_eff:.6f},  σ_eff = {sigma_eff:.6f}"
            ),
            result=round(sigma_eff, 6),
            explanation=(
                "The effective vol is the vol of the ratio F1/F2*. It blends the "
                "individual vols through the weight w and reduces by the cross-term "
                "2ρ·w·σ1·σ2, reflecting the diversification benefit from correlation. "
                "High ρ → lower spread vol → cheaper option (spreads move together)."
            ),
        ))

        # ── Step 3: d1, d2 and Black-76 price ────────────────────────────────
        if F1 > 0 and F2_star > 0 and sigma_eff > 0 and T > 0:
            log_ratio = math.log(F1 / F2_star)
            d1 = (log_ratio + 0.5 * sigma_eff ** 2 * T) / (sigma_eff * sqrt_T)
            d2 = d1 - sigma_eff * sqrt_T
        else:
            d1 = 0.0
            d2 = 0.0
            log_ratio = 0.0

        Nd1 = _norm_cdf(d1)
        Nd2 = _norm_cdf(d2)
        Nnd1 = _norm_cdf(-d1)
        Nnd2 = _norm_cdf(-d2)

        steps.append(CalculationStep(
            step_number=3,
            label="d1, d2 (Black-76 on spread ratio F1/F2*)",
            formula=(
                r"d_1 = \frac{\ln(F_1/F_2^*) + \frac{1}{2}\sigma_{\text{eff}}^2 T}"
                r"{\sigma_{\text{eff}}\sqrt{T}},\quad d_2 = d_1 - \sigma_{\text{eff}}\sqrt{T}"
            ),
            substitution=(
                f"ln(F1/F2*) = ln({F1}/{F2_star:.4f}) = {log_ratio:.6f}.  "
                f"σ_eff·√T = {sigma_eff*sqrt_T:.6f}.  "
                f"d1 = {d1:.6f},  d2 = {d2:.6f}.  "
                f"N(d1) = {Nd1:.6f},  N(d2) = {Nd2:.6f}"
            ),
            result=round(d1, 6),
            explanation=(
                "After the Kirk transformation the spread option becomes a "
                "Black-76 call on the ratio F1/F2*. d1 is positive when F1 > F2* "
                "(spread is above the strike on average over the life of the option)."
            ),
        ))

        # ── Step 4: Option price ──────────────────────────────────────────────
        # Spread call: C = exp(-rT) * [F1*N(d1) - F2**N(d2)]
        # Spread put:  P = exp(-rT) * [F2**N(-d2) - F1*N(-d1)]
        if is_call:
            price = df * (F1 * Nd1 - F2_star * Nd2)
        else:
            price = df * (F2_star * Nnd2 - F1 * Nnd1)

        price = max(price, 0.0)  # numerical floor

        # Intrinsic value (undiscounted)
        raw_spread = F1 - F2 - K
        intrinsic = max(raw_spread, 0.0) if is_call else max(-raw_spread, 0.0)

        steps.append(CalculationStep(
            step_number=4,
            label=f"Kirk spread {'call' if is_call else 'put'} price",
            formula=(
                r"C = e^{-rT}\left[F_1 N(d_1) - F_2^* N(d_2)\right]"
                if is_call else
                r"P = e^{-rT}\left[F_2^* N(-d_2) - F_1 N(-d_1)\right]"
            ),
            substitution=(
                f"DF = {df:.6f}.  "
                + (
                    f"C = {df:.4f}×[{F1}×{Nd1:.4f} - {F2_star:.4f}×{Nd2:.4f}] "
                    f"= {df:.4f}×{F1*Nd1 - F2_star*Nd2:.4f} = {price:.4f}"
                    if is_call else
                    f"P = {df:.4f}×[{F2_star:.4f}×{Nnd2:.4f} - {F1}×{Nnd1:.4f}] "
                    f"= {df:.4f}×{F2_star*Nnd2 - F1*Nnd1:.4f} = {price:.4f}"
                )
                + f".  Raw spread F1-F2-K = {raw_spread:.4f}, intrinsic = {intrinsic:.4f}"
            ),
            result=round(price, 4),
            explanation=(
                f"Kirk's spread {'call' if is_call else 'put'} premium. "
                "The formula looks identical to Black-76 but uses the adjusted "
                "F2* instead of K, ensuring the K=0 limit reduces to Margrabe's "
                "exact exchange option formula."
            ),
        ))

        # ── Step 5: Margrabe bound & approximation quality ───────────────────
        # Margrabe (1978) exchange option K=0: C = exp(-rT)*(F1*N(d1_M) - F2*N(d2_M))
        sigma_marg = math.sqrt(sigma1 ** 2 - 2.0 * rho * sigma1 * sigma2 + sigma2 ** 2)
        if F1 > 0 and F2 > 0 and sigma_marg > 0 and T > 0:
            d1_m = (math.log(F1 / F2) + 0.5 * sigma_marg ** 2 * T) / (sigma_marg * sqrt_T)
            d2_m = d1_m - sigma_marg * sqrt_T
            margrabe = df * (F1 * _norm_cdf(d1_m) - F2 * _norm_cdf(d2_m))
        else:
            margrabe = 0.0

        steps.append(CalculationStep(
            step_number=5,
            label="Margrabe (K=0) exchange option bound",
            formula=(
                r"\sigma_M = \sqrt{\sigma_1^2 - 2\rho\sigma_1\sigma_2 + \sigma_2^2},\quad"
                r"C_M = e^{-rT}\left[F_1 N(d_1^M) - F_2 N(d_2^M)\right]"
            ),
            substitution=(
                f"σ_Margrabe = {sigma_marg:.6f}.  "
                f"Margrabe (K=0) price = {margrabe:.4f}.  "
                f"Kirk (K={K}) price = {price:.4f}.  "
                f"Difference = {margrabe - price:.4f}  "
                f"({'K>0 reduces call value' if is_call and K > 0 else 'put with K>0 increases value' if not is_call and K > 0 else 'K=0: Kirk=Margrabe'})"
            ),
            result=round(margrabe, 4),
            explanation=(
                "Margrabe's formula is exact for the zero-strike exchange option. "
                "Kirk's approximation adds the strike K and should match Margrabe "
                "exactly when K=0. A non-zero positive strike reduces call value "
                "and increases put value relative to the K=0 case."
            ),
        ))

        # ── Step 6: Greeks via finite differences ────────────────────────────
        eps_f = max(F1, F2) * 0.001

        def kirk_price(f1: float, f2: float, k: float, s1: float,
                       s2: float, r_: float, t: float, call: bool) -> float:
            if t <= 0 or s1 <= 0 or s2 <= 0:
                spread = f1 - f2 - k
                return max(spread, 0.0) if call else max(-spread, 0.0)
            df_ = math.exp(-r_ * t)
            f2s = f2 + k * df_
            w_ = f2s / (f1 + f2s)
            var = s1 ** 2 - 2 * rho * w_ * s1 * s2 + (w_ * s2) ** 2
            se = math.sqrt(max(var, 1e-12))
            sq = math.sqrt(t)
            lr = math.log(f1 / f2s) if f1 > 0 and f2s > 0 else 0.0
            _d1 = (lr + 0.5 * se ** 2 * t) / (se * sq)
            _d2 = _d1 - se * sq
            if call:
                return max(df_ * (f1 * _norm_cdf(_d1) - f2s * _norm_cdf(_d2)), 0.0)
            else:
                return max(df_ * (f2s * _norm_cdf(-_d2) - f1 * _norm_cdf(-_d1)), 0.0)

        p_f1u = kirk_price(F1 + eps_f, F2, K, sigma1, sigma2, r, T, is_call)
        p_f1d = kirk_price(F1 - eps_f, F2, K, sigma1, sigma2, r, T, is_call)
        delta1 = (p_f1u - p_f1d) / (2 * eps_f)

        p_f2u = kirk_price(F1, F2 + eps_f, K, sigma1, sigma2, r, T, is_call)
        p_f2d = kirk_price(F1, F2 - eps_f, K, sigma1, sigma2, r, T, is_call)
        delta2 = (p_f2u - p_f2d) / (2 * eps_f)

        eps_v = 0.001
        p_v1u = kirk_price(F1, F2, K, sigma1 + eps_v, sigma2, r, T, is_call)
        vega1 = (p_v1u - price) / eps_v / 100.0  # per 1% vol

        p_v2u = kirk_price(F1, F2, K, sigma1, sigma2 + eps_v, r, T, is_call)
        vega2 = (p_v2u - price) / eps_v / 100.0

        eps_rho = 0.01
        safe_rho = min(rho + eps_rho, 0.9999)

        def kirk_price_rho(rho_: float) -> float:
            if T <= 0:
                sp = F1 - F2 - K
                return max(sp, 0.0) if is_call else max(-sp, 0.0)
            f2s = F2 + K * df
            w_ = f2s / (F1 + f2s)
            var = sigma1 ** 2 - 2 * rho_ * w_ * sigma1 * sigma2 + (w_ * sigma2) ** 2
            se = math.sqrt(max(var, 1e-12))
            lr = math.log(F1 / f2s) if F1 > 0 and f2s > 0 else 0.0
            _d1 = (lr + 0.5 * se ** 2 * T) / (se * sqrt_T)
            _d2 = _d1 - se * sqrt_T
            if is_call:
                return max(df * (F1 * _norm_cdf(_d1) - f2s * _norm_cdf(_d2)), 0.0)
            else:
                return max(df * (f2s * _norm_cdf(-_d2) - F1 * _norm_cdf(-_d1)), 0.0)

        p_rho_up = kirk_price_rho(safe_rho)
        corr_sens = (p_rho_up - price) / eps_rho

        steps.append(CalculationStep(
            step_number=6,
            label="Greeks (finite differences)",
            formula=(
                r"\Delta_1 = \frac{\partial C}{\partial F_1},\quad"
                r"\Delta_2 = \frac{\partial C}{\partial F_2},\quad"
                r"\mathcal{V}_1 = \frac{\partial C}{\partial \sigma_1},\quad"
                r"\rho\text{-sens} = \frac{\partial C}{\partial \rho}"
            ),
            substitution=(
                f"Δ1 = {delta1:.4f} (long F1),  Δ2 = {delta2:.4f} (short F2).  "
                f"Vega1 = {vega1:.4f}/1%σ1,  Vega2 = {vega2:.4f}/1%σ2.  "
                f"ρ-sensitivity = {corr_sens:.4f} per 0.01ρ"
            ),
            result=round(delta1, 4),
            explanation=(
                "Delta1 > 0 (long the first leg), Delta2 < 0 for a call (short the "
                "second leg). Vega2 is typically negative for calls: higher σ2 raises "
                "F2 vol and shrinks the spread. Correlation sensitivity is negative "
                "for calls: higher ρ means F1 and F2 move together → spread narrows."
            ),
        ))

        return SimulatorResult(
            fair_value=round(price, 4),
            method="Kirk's Approximation (spread option)",
            greeks={
                "delta_f1": round(delta1, 6),
                "delta_f2": round(delta2, 6),
                "vega1_1pct": round(vega1, 4),
                "vega2_1pct": round(vega2, 4),
                "rho_sensitivity": round(corr_sens, 4),
            },
            calculation_steps=steps,
            diagnostics={
                "F2_star": round(F2_star, 4),
                "weight_w": round(w, 6),
                "sigma_eff": round(sigma_eff, 6),
                "d1": round(d1, 6),
                "d2": round(d2, 6),
                "N_d1": round(Nd1, 6),
                "N_d2": round(Nd2, 6),
                "discount_factor": round(df, 6),
                "raw_spread": round(raw_spread, 4),
                "intrinsic_value": round(intrinsic, 4),
                "margrabe_K0_price": round(margrabe, 4),
                "sigma_margrabe": round(sigma_marg, 6),
                "call_price": round(
                    price if is_call else kirk_price(F1, F2, K, sigma1, sigma2, r, T, True), 4
                ),
                "put_price": round(
                    price if not is_call else kirk_price(F1, F2, K, sigma1, sigma2, r, T, False), 4
                ),
            },
        )
