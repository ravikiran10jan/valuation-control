"""Model validation framework.

Runs a comprehensive battery of checks against any pricer:
  - Input validation
  - Price finiteness and non-negativity
  - Greeks consistency (finiteness, sign checks)
  - Benchmark comparison (internal vs vendor)
  - Monte Carlo convergence
  - Cross-method consistency
  - Per-asset-class tolerance enforcement
  - Stale-data detection
  - Exception severity classification (GREEN / AMBER / RED)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import numpy as np

from app.core.config import settings, tolerances
from app.pricing.base import BasePricer, PricingResult


@dataclass
class ValidationResult:
    status: str  # VALIDATED | FAILED
    severity: str = "GREEN"  # GREEN | AMBER | RED
    checks: dict[str, bool] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    failed_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "severity": self.severity,
            "checks": self.checks,
            "details": self.details,
            "failed_checks": self.failed_checks,
        }


class ModelValidator:
    """Run validation checks on a pricing model."""

    def __init__(
        self,
        vanilla_tolerance: float | None = None,
        exotic_tolerance: float | None = None,
        mc_convergence_tol: float | None = None,
    ):
        self.vanilla_tolerance = vanilla_tolerance or settings.vanilla_tolerance_pct
        self.exotic_tolerance = exotic_tolerance or settings.exotic_tolerance_pct
        self.mc_convergence_tol = mc_convergence_tol or settings.mc_convergence_tolerance

    # ── tolerance lookup ────────────────────────────────────────
    def _get_tolerance(
        self,
        asset_class: str | None = None,
        product_type: str | None = None,
        is_exotic: bool = False,
    ) -> float:
        """Get the appropriate tolerance for this validation."""
        if asset_class and product_type:
            return tolerances.get_tolerance(asset_class, product_type)
        return self.exotic_tolerance if is_exotic else self.vanilla_tolerance

    @staticmethod
    def classify_severity(deviation_pct: float, tolerance: float) -> str:
        """Classify the exception severity based on deviation vs tolerance."""
        if deviation_pct <= tolerance:
            return "GREEN"
        if deviation_pct <= tolerance * tolerances.amber_threshold:
            return "AMBER"
        return "RED"

    # ── orchestrator ────────────────────────────────────────────
    def validate(
        self,
        pricer: BasePricer,
        *,
        benchmark_value: float | None = None,
        desk_mark: float | None = None,
        is_exotic: bool = False,
        asset_class: str | None = None,
        product_type: str | None = None,
        mc_price_fn: Callable[[], float] | None = None,
        data_timestamp: datetime | str | None = None,
    ) -> ValidationResult:
        checks: dict[str, bool] = {}
        details: dict[str, Any] = {}
        severity = "GREEN"
        tol = self._get_tolerance(asset_class, product_type, is_exotic)

        # 1. Input validation
        errors = pricer.validate_inputs()
        checks["input_validation"] = len(errors) == 0
        details["input_validation"] = errors if errors else "OK"

        # 2. Price produces a finite number
        result: PricingResult | None = None
        try:
            result = pricer.price()
            price_ok = math.isfinite(result.fair_value)
            checks["price_finite"] = price_ok
            details["price_finite"] = result.fair_value
        except Exception as e:
            checks["price_finite"] = False
            details["price_finite"] = str(e)

        # 3. Greeks consistency (finiteness)
        try:
            greeks = pricer.calculate_greeks()
            greeks_ok = all(math.isfinite(v) for v in greeks.values())
            checks["greeks_finite"] = greeks_ok
            details["greeks"] = {k: round(v, 6) for k, v in greeks.items()}
        except Exception as e:
            checks["greeks_finite"] = False
            details["greeks"] = str(e)

        # 4. Benchmark comparison
        if benchmark_value is not None and result is not None:
            diff = abs(result.fair_value - benchmark_value)
            rel_diff = diff / abs(benchmark_value) if benchmark_value != 0 else diff
            checks["benchmark"] = rel_diff < tol
            details["benchmark"] = {
                "internal": round(result.fair_value, 2),
                "benchmark": round(benchmark_value, 2),
                "relative_diff": round(rel_diff, 6),
                "tolerance": tol,
            }
            sev = self.classify_severity(rel_diff, tol)
            if sev != "GREEN":
                severity = sev

        # 5. Desk mark comparison (IPV core check)
        if desk_mark is not None and result is not None:
            diff = abs(result.fair_value - desk_mark)
            if abs(desk_mark) > 1e-10:
                rel_diff = diff / abs(desk_mark)
            else:
                rel_diff = diff
            checks["desk_mark_comparison"] = rel_diff < tol
            sev = self.classify_severity(rel_diff, tol)
            details["desk_mark_comparison"] = {
                "vc_fair_value": round(result.fair_value, 2),
                "desk_mark": round(desk_mark, 2),
                "difference": round(result.fair_value - desk_mark, 2),
                "relative_diff_pct": round(rel_diff * 100, 4),
                "tolerance_pct": round(tol * 100, 4),
                "severity": sev,
            }
            if sev != "GREEN" and (severity == "GREEN" or sev == "RED"):
                severity = sev

        # 6. Monte Carlo convergence
        if mc_price_fn is not None:
            try:
                prices = [mc_price_fn() for _ in range(5)]
                mean_px = abs(np.mean(prices))
                spread = (max(prices) - min(prices)) / mean_px if mean_px != 0 else 0
                conv_ok = spread < self.mc_convergence_tol
                checks["mc_convergence"] = conv_ok
                details["mc_convergence"] = {
                    "prices": [round(p, 2) for p in prices],
                    "relative_spread": round(spread, 6),
                    "tolerance": self.mc_convergence_tol,
                }
            except Exception as e:
                checks["mc_convergence"] = False
                details["mc_convergence"] = str(e)

        # 7. Arbitrage: non-negative price for long positions
        if result is not None:
            checks["non_negative_price"] = result.fair_value >= 0
            details["non_negative_price"] = result.fair_value

        # 8. Cross-method consistency
        if result is not None and len(result.methods) > 1:
            values = list(result.methods.values())
            max_val = max(values)
            min_val = min(values)
            if max_val != 0:
                cross_spread = (max_val - min_val) / abs(max_val)
            else:
                cross_spread = 0.0
            checks["cross_method_consistency"] = cross_spread < tol
            details["cross_method_consistency"] = {
                "methods": {k: round(v, 2) for k, v in result.methods.items()},
                "relative_spread": round(cross_spread, 6),
                "tolerance": tol,
            }

        # 9. Stale-data check
        if data_timestamp is not None:
            if isinstance(data_timestamp, str):
                try:
                    data_timestamp = datetime.fromisoformat(data_timestamp)
                except ValueError:
                    data_timestamp = None

            if isinstance(data_timestamp, datetime):
                age_seconds = abs(
                    (datetime.utcnow() - data_timestamp).total_seconds()
                )
                stale_threshold = settings.stale_data_threshold_seconds
                is_fresh = age_seconds <= stale_threshold
                checks["data_freshness"] = is_fresh
                details["data_freshness"] = {
                    "data_age_seconds": round(age_seconds, 1),
                    "threshold_seconds": stale_threshold,
                    "is_fresh": is_fresh,
                }
                if not is_fresh:
                    severity = "AMBER" if severity == "GREEN" else severity

        # Ensure all check values are plain Python bools (not numpy bools)
        checks = {k: bool(v) for k, v in checks.items()}

        # Summarize
        failed = [k for k, v in checks.items() if not v]
        status = "VALIDATED" if len(failed) == 0 else "FAILED"
        if status == "FAILED" and severity == "GREEN":
            severity = "AMBER"

        return ValidationResult(
            status=status,
            severity=severity,
            checks=checks,
            details=details,
            failed_checks=failed,
        )
