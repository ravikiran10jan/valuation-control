# Derivative Pricing Simulator — Implementation Plan

## Overview

A dynamic, interactive derivative pricing simulator module integrated into the existing
valuation control platform. Users select a **product type → model**, load a **sample with
prepopulated parameters** (or enter custom), see the **formula with step-by-step calculations**,
and get **results with Greeks**. Every model carries a clear description of **when to use / when NOT to use**.

Priority is aligned to the interviewer's direct hands-on experience (BofA ValControl, Credit Suisse Model Validation, Smart Cube Derivative Pricing, Pyxis Exotic Pricing).

---

## Architecture

### Design Principles

- **Registry Pattern** — Every model self-registers with metadata, formulas, samples, and applicability rules
- **Self-Contained Models** — Each model file is a standalone unit: metadata + parameters schema + samples + formula + calculate + step-by-step trace
- **Dynamic Discovery** — API auto-discovers all registered models; frontend renders dynamically
- **Extend, Don't Break** — New `simulator/` module sits alongside existing `pricing/`; existing pricers untouched

### New Directory Structure

```
agent2-pricing-engine/
  app/
    simulator/
    ├── __init__.py
    ├── registry.py                  # ModelRegistry: auto-discovery, listing, lookup
    ├── base.py                      # BaseSimulatorModel ABC
    ├── schemas.py                   # Pydantic request/response for simulator API
    │
    ├── models/
    │   ├── __init__.py
    │   │
    │   ├── equity/
    │   │   ├── __init__.py
    │   │   ├── black_scholes.py         # P0 — BSM European options
    │   │   ├── cev.py                   # P0 — Constant Elasticity of Variance
    │   │   ├── variance_gamma.py        # P0 — Variance Gamma (FFT)
    │   │   ├── binomial_tree.py         # P0 — CRR Binomial (American)
    │   │   ├── heston.py                # P1 — Stochastic vol
    │   │   ├── local_vol_dupire.py      # P0 — Dupire local vol
    │   │   ├── rainbow_basket.py        # P1 — Multi-asset correlated MC
    │   │   ├── convertible_bond.py      # P1 — TF model with credit
    │   │   └── warrant.py               # P1 — Dilution-adjusted BSM
    │   │
    │   ├── fx/
    │   │   ├── __init__.py
    │   │   ├── garman_kohlhagen.py      # P0 — FX vanilla options
    │   │   ├── fx_forward_cip.py        # P0 — Covered Interest Parity
    │   │   ├── vanna_volga.py           # P1 — FX smile method
    │   │   ├── fx_barrier.py            # P1 — Knock-in/out (analytical + MC)
    │   │   └── tarf.py                  # P1 — Target Redemption Forward (MC)
    │   │
    │   ├── rates/
    │   │   ├── __init__.py
    │   │   ├── irs_multicurve.py        # P1 — IRS dual-curve DCF
    │   │   ├── black76_capfloor.py      # P1 — Caps/Floors
    │   │   ├── hull_white_1f.py         # P0 — Short rate model
    │   │   ├── bdt.py                   # P1 — Black-Derman-Toy lattice
    │   │   └── swaption_bachelier.py    # P1 — Normal vol swaption
    │   │
    │   ├── credit/
    │   │   ├── __init__.py
    │   │   ├── cds_isda.py              # P1 — ISDA standard CDS
    │   │   ├── first_to_default.py      # P0 — Basket CDS (Gaussian Copula)
    │   │   ├── merton_structural.py     # P1 — Firm value model
    │   │   └── gaussian_copula.py       # P1 — CDO tranche pricing
    │   │
    │   └── commodity/
    │       ├── __init__.py
    │       ├── black76_commodity.py     # P1 — Options on futures
    │       └── spread_kirk.py           # P2 — Crack/spark spread
    │
    └── api/
        └── routes.py                    # /simulator/* endpoints

agent7-dashboard/
  src/
    components/
      simulator/
      ├── SimulatorPage.tsx               # Main page with 3-panel layout
      ├── ProductModelSelector.tsx        # Left panel: product → model tree
      ├── SampleSelector.tsx              # Dropdown of preloaded samples
      ├── ParameterForm.tsx               # Dynamic form from parameter schema
      ├── FormulaDisplay.tsx              # LaTeX/MathJax formula rendering
      ├── CalculationSteps.tsx            # Step-by-step calculation trace
      ├── ResultsPanel.tsx                # Fair value, Greeks, diagnostics
      └── ApplicabilityCard.tsx           # When to use / when NOT to use
```

---

## BaseSimulatorModel — Interface Contract

Every model implements this ABC:

```python
class BaseSimulatorModel(ABC):
    """Every simulator model must implement this interface."""

    # ── Identity ──
    model_id: str              # e.g. "black_scholes"
    model_name: str            # e.g. "Black-Scholes-Merton"
    product_type: str          # e.g. "European Vanilla Option"
    asset_class: str           # e.g. "equity" | "fx" | "rates" | "credit" | "commodity"

    # ── Description ──
    short_description: str     # 1-line summary
    long_description: str      # Full paragraph explaining the model

    # ── Applicability Rules ──
    when_to_use: list[str]     # Bullet points: when this model is appropriate
    when_not_to_use: list[str] # Bullet points: when this model breaks down
    assumptions: list[str]     # Key model assumptions
    limitations: list[str]     # Known limitations

    # ── Formula ──
    formula_latex: str         # LaTeX string for rendering
    formula_plain: str         # Plain-text fallback

    # ── Parameters ──
    parameters_schema: dict    # JSON Schema for all input parameters
    sample_sets: dict[str, dict]  # Named samples with prepopulated params

    # ── Compute ──
    @abstractmethod
    def calculate(self, params: dict) -> SimulatorResult

    @abstractmethod
    def calculation_steps(self, params: dict) -> list[CalculationStep]

    def calculate_greeks(self, params: dict) -> dict[str, float]
```

### SimulatorResult

```python
@dataclass
class SimulatorResult:
    fair_value: float
    method: str
    greeks: dict[str, float]
    calculation_steps: list[CalculationStep]
    diagnostics: dict[str, Any]

@dataclass
class CalculationStep:
    step_number: int
    label: str           # e.g. "Calculate d1"
    formula: str         # e.g. "d1 = [ln(S/K) + (r - q + σ²/2)T] / (σ√T)"
    substitution: str    # e.g. "d1 = [ln(100/105) + (0.05 - 0 + 0.04/2)×1] / (0.2×1)"
    result: float        # e.g. -0.0127
    explanation: str     # e.g. "d1 measures how many std devs the option is in/out of the money"
```

---

## Model Registry

```python
class ModelRegistry:
    """Singleton registry — models self-register on import."""

    _models: dict[str, BaseSimulatorModel] = {}

    @classmethod
    def register(cls, model_class):
        """Decorator: @ModelRegistry.register"""
        instance = model_class()
        cls._models[instance.model_id] = instance
        return model_class

    @classmethod
    def list_products(cls) -> dict[str, list[dict]]:
        """Return {asset_class: [{model_id, model_name, product_type}]}"""

    @classmethod
    def get_model(cls, model_id: str) -> BaseSimulatorModel

    @classmethod
    def get_samples(cls, model_id: str) -> dict[str, dict]
```

---

## API Endpoints

```
GET  /simulator/products
     → { "equity": [...], "fx": [...], "rates": [...], "credit": [...], "commodity": [...] }

GET  /simulator/models/{model_id}
     → Full model metadata: description, when_to_use, when_not_to_use,
       assumptions, limitations, formula_latex, parameters_schema, sample_sets

GET  /simulator/models/{model_id}/samples
     → { "atm_call": {...}, "otm_put": {...}, "deep_itm": {...} }

POST /simulator/calculate
     body: { model_id, parameters }
     → { fair_value, greeks, calculation_steps[], diagnostics }

POST /simulator/compare
     body: { model_ids: [...], parameters }
     → Side-by-side results from multiple models (e.g. BSM vs CEV vs VG)
```

---

## Phase 0 — Foundation & The Model Comparison Story
*Maps to interviewer's Pyxis Systems work: BSM vs CEV vs Variance Gamma for LEAPS*

### Models to Build

#### 1. Black-Scholes-Merton (`black_scholes.py`)

**When to use:**
- European vanilla options (no early exercise)
- Liquid markets with reasonably stable volatility
- Quick indicative pricing and hedging
- Baseline comparison model for any option pricing

**When NOT to use:**
- American options (doesn't handle early exercise)
- Deep OTM/ITM options where smile/skew matters
- Long-dated options where vol-of-vol is significant
- Products with path-dependency (barriers, Asians)
- Markets with jumps (emerging markets, earnings events)
- When the underlying pays discrete dividends (use modified BSM)

**Samples:**
| Sample Name | S | K | T | σ | r | q | Type |
|---|---|---|---|---|---|---|---|
| ATM Call (AAPL-like) | 185.0 | 185.0 | 0.25 | 0.22 | 0.053 | 0.005 | call |
| OTM Put (SPX-like) | 5200 | 4900 | 0.5 | 0.18 | 0.053 | 0.015 | put |
| Deep ITM LEAPS Call | 150 | 100 | 2.0 | 0.30 | 0.05 | 0.01 | call |
| Near-expiry ATM | 100 | 100 | 0.02 | 0.25 | 0.05 | 0.0 | call |

**Calculation Steps:**
1. Compute d1 = [ln(S/K) + (r - q + σ²/2)T] / (σ√T)
2. Compute d2 = d1 - σ√T
3. Compute N(d1) and N(d2) — cumulative normal
4. Call = S·e^(-qT)·N(d1) - K·e^(-rT)·N(d2)
5. Put = K·e^(-rT)·N(-d2) - S·e^(-qT)·N(-d1)
6. Greeks: Δ, Γ, V, Θ, ρ (analytical)

---

#### 2. CEV — Constant Elasticity of Variance (`cev.py`)

**When to use:**
- When you observe leverage effect (vol increases as spot decreases)
- Equity options where skew is important but you want a parsimonious model
- When BSM flat-vol assumption is too crude but stochastic vol is overkill
- Comparing model risk: how much does the β parameter change the price?
- LEAPS and long-dated options where leverage effect compounds

**When NOT to use:**
- When β = 2 (reduces to BSM — no advantage)
- Products requiring smile dynamics (term structure of skew)
- Path-dependent exotics (no efficient closed-form)
- When you need to capture vol-of-vol (use Heston/SABR instead)
- Very low spot values (numerical instability as S→0 when β < 2)

**Key insight:** CEV nests BSM (β=2) and normal model (β=0). The parameter β controls how volatility responds to spot: σ(S) = σ₀ · S^(β/2 - 1)

**Samples:**
| Sample Name | S | K | T | σ₀ | β | r | Type |
|---|---|---|---|---|---|---|---|
| Equity with leverage (β=1.5) | 100 | 100 | 1.0 | 0.20 | 1.5 | 0.05 | call |
| Normal model (β=0) | 100 | 100 | 1.0 | 20.0 | 0.0 | 0.05 | call |
| BSM equivalent (β=2) | 100 | 100 | 1.0 | 0.20 | 2.0 | 0.05 | call |
| Strong leverage (β=0.5) | 100 | 100 | 1.0 | 0.20 | 0.5 | 0.05 | call |

**Calculation Steps:**
1. Check β value and select method (analytical via non-central chi-squared, or PDE)
2. For β < 2: Transform to non-central chi-squared distribution
3. Compute k = 2(r-q) / [σ₀²(2-β)(e^((r-q)(2-β)T) - 1)]
4. Compute x = k·S^(2-β)·e^((r-q)(2-β)T) and y = k·K^(2-β)
5. Call = S·e^(-qT)·[1 - χ²(2y; 2+2/(2-β), 2x)] - K·e^(-rT)·χ²(2x; 2/(2-β), 2y)
6. Show comparison with BSM price for same parameters

---

#### 3. Variance Gamma (`variance_gamma.py`)

**When to use:**
- When you observe excess kurtosis (fat tails) AND skewness in returns
- Pricing options where jump risk matters (earnings, EM currencies)
- When BSM underprices OTM puts and overprices OTM calls
- LEAPS where non-normality of returns compounds over time
- Model comparison: shows impact of relaxing the normality assumption

**When NOT to use:**
- When market behaves close to log-normal (simple liquid equities)
- Real-time hedging (harder to delta-hedge, incomplete market)
- Path-dependent exotics (MC required, slow for VG)
- When you need stochastic volatility dynamics (VG has no vol-of-vol)
- Calibration to full vol surface (VG has limited parameters)

**Key insight:** VG = Brownian motion evaluated at a random (gamma) time. Three parameters: σ (vol of BM), θ (drift of BM → skew), ν (variance of gamma time → kurtosis).

**Samples:**
| Sample Name | S | K | T | σ | θ | ν | r | Type |
|---|---|---|---|---|---|---|---|---|
| Fat tails, no skew | 100 | 100 | 1.0 | 0.20 | 0.0 | 0.25 | 0.05 | call |
| Negative skew (equity-like) | 100 | 100 | 1.0 | 0.20 | -0.15 | 0.25 | 0.05 | put |
| High kurtosis (EM) | 100 | 95 | 0.5 | 0.30 | -0.10 | 0.50 | 0.08 | put |
| BSM-like (ν→0) | 100 | 100 | 1.0 | 0.20 | 0.0 | 0.001 | 0.05 | call |

**Calculation Steps:**
1. Compute the VG characteristic function: φ(u)
2. Compute the risk-neutral drift correction: ω = (1/ν)·ln(1 - θν - σ²ν/2)
3. Apply Carr-Madan FFT pricing:
   a. Define modified call price in Fourier space
   b. Set damping parameter α
   c. Apply FFT with N grid points
   d. Interpolate to get price at target strike
4. Compare with BSM price (set θ=0, ν→0)

---

#### 4. Delta Hedging Simulator (`hedge_simulator.py`)

**Purpose:** Compare hedging effectiveness across BSM, CEV, and VG models.

This is NOT a pricing model but a **simulation framework** that:
1. Simulates stock price paths under a chosen "real-world" process (e.g., VG with jumps)
2. Hedges a sold option using deltas from each of the three models
3. Computes hedging P&L, tracking error, and distribution of final P&L
4. Shows that **model misspecification** leads to systematic hedging error

**Samples:**
| Scenario | True Process | Hedge Using | Rebalance Freq |
|---|---|---|---|
| BSM world, BSM hedge | GBM (σ=20%) | BSM | Daily |
| VG world, BSM hedge | VG (σ=20%, θ=-0.15, ν=0.25) | BSM | Daily |
| VG world, VG hedge | VG (σ=20%, θ=-0.15, ν=0.25) | VG | Daily |
| CEV world, BSM hedge | CEV (β=1.5) | BSM | Daily |
| Impact of rebalance freq | GBM | BSM | Daily vs Weekly vs Monthly |

---

## Phase 1 — PDE Framework
*Maps to interviewer's Credit Suisse work: independent PDE pricer implementation*

### 5. Generic PDE Solver (`pde_solver.py`)

A reusable **Crank-Nicolson finite-difference** engine that any model can plug into.

**When to use PDE:**
- 1D or 2D problems (up to 2 state variables)
- Barrier options with continuous monitoring
- American options (via penalty method or projected SOR)
- Local volatility pricing
- Convertible bonds (equity + credit boundary)

**When NOT to use PDE:**
- High-dimensional problems (> 2-3 factors) — use Monte Carlo
- Path-dependent payoffs (Asian, lookback) unless reformulated
- When closed-form exists (use analytical for speed)

**Calculation Steps (shown to user):**
1. Define spatial grid: S_min to S_max with N_S points
2. Define time grid: 0 to T with N_t steps
3. Set boundary conditions (Dirichlet/Neumann)
4. Set terminal condition (payoff at expiry)
5. At each time step: solve tridiagonal system (Crank-Nicolson θ-scheme)
6. For American: apply early exercise constraint at each step
7. Extract price at S = S_current

### 6. Local Volatility — Dupire (`local_vol_dupire.py`)

**When to use:**
- When you need to exactly fit today's entire implied vol surface
- Pricing barriers and path-dependent exotics consistently with vanillas
- As the "local" component in a Local-Stochastic Vol (LSV) hybrid
- Model validation: comparing exotic prices across model choices

**When NOT to use:**
- Forward-starting options (Dupire has unrealistic forward smile dynamics)
- Cliquets, autocallables (smile dynamics matter more than fit-to-today)
- When vol surface data is sparse (Dupire amplifies noise)
- If you only have ATM vol (need a full surface)

**Calculation Steps:**
1. From market implied vols, compute call prices C(K,T) on a grid
2. Apply Dupire formula: σ_local²(K,T) = [∂C/∂T + (r-q)K·∂C/∂K + qC] / [½K²·∂²C/∂K²]
3. Interpolate local vol surface
4. Price exotic via PDE with σ(S,t) = σ_local(S,t)

### 7. Hull-White 1-Factor (`hull_white_1f.py`)

**When to use:**
- Bermudan swaptions, callable bonds
- Any product with early exercise on interest rates
- When you need to calibrate to the term structure of swaption vols
- Building blocks for hybrid models (rates component in PRDC, etc.)

**When NOT to use:**
- When two-factor dynamics are needed (butterfly swaptions, CMS spread options)
- Very long-dated products where mean reversion uncertainty dominates
- When negative rates are a concern and you need log-normal dynamics (use Black-Karasinski)
- Products sensitive to vol smile (HW is single-vol, no smile)

**Calculation Steps:**
1. Calibrate mean reversion κ and vol σ to swaption vols
2. Build trinomial tree: dr = κ(θ(t) - r)dt + σdW
3. θ(t) chosen to fit the initial yield curve exactly
4. Backward induction for Bermudan exercise decisions
5. Price = expected discounted payoff with optimal exercise

---

## Phase 2 — Credit Exotics
*Maps to interviewer's Smart Cube work: first-to-default CDS, default modeling*

### 8. First-to-Default Basket CDS (`first_to_default.py`)

**When to use:**
- Basket credit derivatives (nth-to-default swaps)
- When you need to price correlation-dependent credit products
- Understanding how default correlation drives basket spread

**When NOT to use:**
- Single-name CDS (use ISDA standard model)
- When you need dynamic correlation (Gaussian Copula is static)
- Bespoke tranches with complex subordination (need full loss distribution)

**Calculation Steps:**
1. Bootstrap marginal hazard rate curves from individual CDS spreads
2. Generate correlated default times using Gaussian Copula:
   a. Generate correlated standard normals (Cholesky)
   b. Transform to uniform via Φ(z)
   c. Invert marginal survival functions to get default times
3. Determine first default time τ₁ = min(τ₁, τ₂, ..., τₙ)
4. Price protection leg: E[discount × (1-R) × 1{τ₁ ≤ T}]
5. Price premium leg: E[Σ discount × spread × Δt × 1{τ₁ > tᵢ}]
6. Par spread = Protection Leg / Risky Annuity

### 9. CDS — ISDA Standard Model (`cds_isda.py`)

### 10. Merton Structural Model (`merton_structural.py`)

**When to use:**
- Estimating default probability from equity prices
- Understanding credit-equity linkage
- Academic/educational context for credit risk

**When NOT to use:**
- Pricing tradeable credit instruments (use reduced-form)
- When firm value is not observable (always — it's a theoretical construct)
- Short-term default prediction (structural models underestimate short-term default)

---

## Phase 3 — FX & Rates Production
*Maps to interviewer's FX options VaR, TARFs, and current BofA role*

### 11. Garman-Kohlhagen (`garman_kohlhagen.py`)
BSM extended to FX with domestic and foreign rates.

### 12. FX Forward — Covered Interest Parity (`fx_forward_cip.py`)
F = S × e^((r_dom - r_for) × T)

### 13. TARF — Target Redemption Forward (`tarf.py`)

**When to use:**
- Structured FX forwards with embedded barriers on accumulated gain
- Common in Asia-Pacific corporate hedging
- When client wants leveraged forward with cap on total gain

**When NOT to use:**
- Simple FX hedging (use vanilla forwards)
- When analytical pricing is needed (TARFs require Monte Carlo)
- When you don't have reliable vol surface (sensitive to smile)

### 14. Vanna-Volga (`vanna_volga.py`)
FX-specific smile pricing method using 25D RR, 25D BF, ATM quotes.

### 15. IRS Multi-Curve DCF (`irs_multicurve.py`)
Post-crisis OIS discounting + forward rate projection.

### 16. Cap/Floor Black-76 (`black76_capfloor.py`)

### 17. Swaption Bachelier/Normal (`swaption_bachelier.py`)

---

## Phase 4 — Valuation Control Extensions
*Maps to interviewer's current BofA role: IPV, AVA, PruVal, FVH, CCAR*

### 18. Model Comparison Engine
Side-by-side pricing from multiple models for the same product. Shows:
- Price differences (model reserve = max - min)
- Greek differences
- Parameter sensitivity comparison

### 19. Applicability Matrix
A cross-reference: for each product, which models are valid, which are preferred,
and what the key differentiators are.

---

## Frontend Design — Simulator Page

### 3-Panel Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Derivative Pricing Simulator                          [Compare Mode]  │
├──────────────┬──────────────────────────────────────────────────────────┤
│              │                                                          │
│  PRODUCT &   │  ┌─ FORMULA ──────────────────────────────────────────┐ │
│  MODEL       │  │                                                    │ │
│              │  │  C = S·e^(-qT)·N(d₁) - K·e^(-rT)·N(d₂)          │ │
│  ▼ Equity    │  │                                                    │ │
│    ● BSM  ←  │  │  where d₁ = [ln(S/K) + (r-q+σ²/2)T] / σ√T      │ │
│    ○ CEV     │  │        d₂ = d₁ - σ√T                              │ │
│    ○ VG      │  │                                                    │ │
│    ○ Binom   │  └────────────────────────────────────────────────────┘ │
│    ○ Heston  │                                                          │
│              │  ┌─ APPLICABILITY ─────────────────────────────────────┐ │
│  ▶ FX        │  │ ✓ USE: European vanillas, liquid markets, baseline │ │
│  ▶ Rates     │  │ ✗ NOT: American exercise, barriers, jumps, skew   │ │
│  ▶ Credit    │  │ ⚠ Assumes: constant vol, continuous trading,      │ │
│  ▶ Commodity │  │   log-normal returns, no transaction costs         │ │
│              │  └────────────────────────────────────────────────────┘ │
│──────────────│                                                          │
│              │  ┌─ PARAMETERS ───────────────────────────────────────┐ │
│  SAMPLE      │  │ Sample: [ATM Call (AAPL-like) ▼]                   │ │
│  [ATM Call ▼]│  │                                                    │ │
│              │  │ Spot (S):     185.00    Strike (K):  185.00        │ │
│              │  │ Maturity (T): 0.25 yr   Vol (σ):     22%          │ │
│              │  │ Rate (r):     5.3%      Div yield:   0.5%         │ │
│              │  │ Type:         [Call ▼]                              │ │
│              │  │                                    [Calculate →]    │ │
│              │  └────────────────────────────────────────────────────┘ │
│              │                                                          │
│              │  ┌─ CALCULATION STEPS ────────────────────────────────┐ │
│              │  │                                                    │ │
│              │  │ Step 1: Calculate d₁                               │ │
│              │  │ d₁ = [ln(185/185) + (0.053-0.005+0.0242)×0.25]   │ │
│              │  │      / (0.22 × √0.25)                             │ │
│              │  │ d₁ = [0 + 0.01805] / 0.11 = 0.1641               │ │
│              │  │                                                    │ │
│              │  │ Step 2: Calculate d₂                               │ │
│              │  │ d₂ = 0.1641 - 0.11 = 0.0541                      │ │
│              │  │                                                    │ │
│              │  │ Step 3: Calculate N(d₁) and N(d₂)                 │ │
│              │  │ N(0.1641) = 0.5652                                │ │
│              │  │ N(0.0541) = 0.5216                                │ │
│              │  │                                                    │ │
│              │  │ Step 4: Calculate call price                       │ │
│              │  │ C = 185×e^(-0.00125)×0.5652                       │ │
│              │  │   - 185×e^(-0.01325)×0.5216                       │ │
│              │  │ C = 104.50 - 95.35 = $9.15                        │ │
│              │  └────────────────────────────────────────────────────┘ │
│              │                                                          │
│              │  ┌─ RESULTS ──────────────────────────────────────────┐ │
│              │  │ Fair Value:  $9.15        Method: Black-Scholes    │ │
│              │  │                                                    │ │
│              │  │ Greeks:                                             │ │
│              │  │ Δ  +0.5625   Γ  0.0362   V  18.32                 │ │
│              │  │ Θ  -14.72/yr  ρ  22.85                            │ │
│              │  └────────────────────────────────────────────────────┘ │
└──────────────┴──────────────────────────────────────────────────────────┘
```

### Compare Mode
When enabled, user selects 2-3 models and sees results side-by-side:
```
┌─────────────────────────────────────────────────────┐
│  Model Comparison: LEAPS Call (S=150, K=100, T=2yr) │
├─────────────────┬──────────┬──────────┬─────────────┤
│                 │   BSM    │   CEV    │     VG      │
│                 │          │  (β=1.5) │ (θ=-0.15)   │
├─────────────────┼──────────┼──────────┼─────────────┤
│ Fair Value      │  $58.42  │  $57.18  │   $56.93    │
│ Delta           │  +0.892  │  +0.885  │   +0.881    │
│ Gamma           │  0.0051  │  0.0048  │   0.0046    │
│ Vega            │  24.31   │  22.87   │   21.95     │
│ Model Reserve   │          $1.49 (max-min)           │
└─────────────────┴──────────┴──────────┴─────────────┘
```

---

## Build Sequence Summary

| Phase | Models | Count | Backend Files | Frontend Files |
|---|---|---|---|---|
| **P0: Foundation** | BaseModel, Registry, API scaffold, BSM, CEV, VG, Hedge Simulator | 4 models + framework | ~10 files | ~8 files |
| **P1: PDE + Short Rates** | PDE Solver, Local Vol, Hull-White, Binomial, Heston | 5 models | ~6 files | 0 (reuses P0 UI) |
| **P2: Credit** | First-to-Default, CDS ISDA, Merton Structural | 3 models | ~4 files | 0 |
| **P3: FX & Rates** | GK, FX Forward, TARF, Vanna-Volga, IRS, Cap/Floor, Swaption | 7 models | ~8 files | 0 |
| **P4: ValControl** | Model Comparison Engine, Applicability Matrix | 2 tools | ~3 files | ~2 files |
| **Total** | | **21 models + 2 tools** | ~31 files | ~10 files |

---

## Tech Decisions

- **Formula rendering:** KaTeX (lighter than MathJax, SSR-friendly, already npm-installable)
- **Parameter forms:** Auto-generated from JSON Schema (each model declares its own schema)
- **No new database tables:** Simulator is stateless — compute on demand
- **No new Docker service:** Lives inside existing agent2 (backend) and agent7 (frontend)
- **Testing:** Each model gets a test with known analytical results (e.g., BSM vs textbook values)
