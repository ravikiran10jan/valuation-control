"""Greeks Variance Analysis — Desk vs Valuation Control (VC) Comparison.

Compares front-office (desk) Greeks against independently computed
Valuation Control (VC) Greeks and identifies root causes for variances.

Variance thresholds (from Excel Greeks_PnL_Attribution sheet):
    Delta variance  >  5%   =>  Flag
    Gamma variance  > 10%   =>  Flag
    Vega variance   >  5%   =>  Flag
    Theta variance  >  5%   =>  Flag

Root cause categories with typical distribution:
    Market Data Timing:   45%
    Vol Surface Diff:     25%
    Trade Pop Mismatch:   15%
    Calc Method:           8%
    Model Version:         4%
    Rounding:              2%
    Other:                 1%
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants and thresholds
# ---------------------------------------------------------------------------

# Per-Greek variance thresholds (percentage)
VARIANCE_THRESHOLDS: dict[str, float] = {
    "delta": 5.0,     # 5% variance threshold
    "gamma": 10.0,    # 10% variance threshold (wider due to gamma instability)
    "vega": 5.0,      # 5% variance threshold
    "theta": 5.0,     # 5% variance threshold
    "rho": 10.0,      # 10% variance threshold
    "vanna": 15.0,    # 15% (second-order, more volatile)
    "volga": 15.0,    # 15% (second-order, more volatile)
}


class RootCauseCategory(str, Enum):
    """Root cause categories for Greek variances."""

    MARKET_DATA_TIMING = "Market Data Timing"
    VOL_SURFACE_DIFF = "Vol Surface Diff"
    TRADE_POP_MISMATCH = "Trade Pop Mismatch"
    CALC_METHOD = "Calc Method"
    MODEL_VERSION = "Model Version"
    ROUNDING = "Rounding"
    OTHER = "Other"


# Typical root cause distribution (from Excel analysis)
ROOT_CAUSE_DISTRIBUTION: dict[str, float] = {
    RootCauseCategory.MARKET_DATA_TIMING.value: 0.45,
    RootCauseCategory.VOL_SURFACE_DIFF.value: 0.25,
    RootCauseCategory.TRADE_POP_MISMATCH.value: 0.15,
    RootCauseCategory.CALC_METHOD.value: 0.08,
    RootCauseCategory.MODEL_VERSION.value: 0.04,
    RootCauseCategory.ROUNDING.value: 0.02,
    RootCauseCategory.OTHER.value: 0.01,
}

# Root cause identification rules (heuristic-based)
# Each rule maps a condition to a likely root cause
ROOT_CAUSE_RULES = {
    RootCauseCategory.MARKET_DATA_TIMING: {
        "description": (
            "Desk and VC use different market data snapshots. "
            "FX spot, vol, or rate data captured at different times."
        ),
        "indicators": [
            "All Greeks shifted in same direction",
            "Variance correlates with market movement magnitude",
            "Variance largest during high-volatility periods",
        ],
        "typical_impact_pct": 45,
    },
    RootCauseCategory.VOL_SURFACE_DIFF: {
        "description": (
            "Different vol surface construction or interpolation methods. "
            "SABR params, smile fitting, or skew treatment differ."
        ),
        "indicators": [
            "Vega variance is dominant",
            "Gamma also shows variance (vol-dependent)",
            "Delta variance is relatively small",
        ],
        "typical_impact_pct": 25,
    },
    RootCauseCategory.TRADE_POP_MISMATCH: {
        "description": (
            "Trade population differs between desk and VC systems. "
            "Missing trades, cancelled trades, or settlement mismatches."
        ),
        "indicators": [
            "Large absolute variance in delta and notional",
            "All Greeks proportionally off by similar factor",
            "Specific trade IDs missing from one system",
        ],
        "typical_impact_pct": 15,
    },
    RootCauseCategory.CALC_METHOD: {
        "description": (
            "Different numerical methods for Greek computation. "
            "Bump size, finite-difference scheme, or analytical vs numeric."
        ),
        "indicators": [
            "Gamma variance dominant (most sensitive to bump size)",
            "Theta affected by day-count convention differences",
            "Vega affected by vol-bump convention",
        ],
        "typical_impact_pct": 8,
    },
    RootCauseCategory.MODEL_VERSION: {
        "description": (
            "Desk and VC running different model versions or calibrations. "
            "Parameter updates not synchronized."
        ),
        "indicators": [
            "Consistent bias across all Greeks",
            "Variance appeared after model update date",
            "Specific to certain product types",
        ],
        "typical_impact_pct": 4,
    },
    RootCauseCategory.ROUNDING: {
        "description": (
            "Precision differences in intermediate calculations. "
            "Floating-point rounding in different environments."
        ),
        "indicators": [
            "Very small absolute variance",
            "Variance < 0.01% in most cases",
            "Consistent across all product types",
        ],
        "typical_impact_pct": 2,
    },
    RootCauseCategory.OTHER: {
        "description": "Unclassified variance requiring manual investigation.",
        "indicators": ["Does not match any known pattern"],
        "typical_impact_pct": 1,
    },
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GreekVariance:
    """Variance analysis for a single Greek."""

    greek_name: str
    desk_value: float
    vc_value: float
    absolute_variance: float
    relative_variance_pct: float
    threshold_pct: float
    is_flagged: bool
    flag_severity: str
    likely_root_causes: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "greek_name": self.greek_name,
            "desk_value": round(self.desk_value, 6),
            "vc_value": round(self.vc_value, 6),
            "absolute_variance": round(self.absolute_variance, 6),
            "relative_variance_pct": round(self.relative_variance_pct, 4),
            "threshold_pct": self.threshold_pct,
            "is_flagged": self.is_flagged,
            "flag_severity": self.flag_severity,
            "likely_root_causes": self.likely_root_causes,
        }


@dataclass
class VarianceAnalysisResult:
    """Complete variance analysis result for a position."""

    position_id: str
    analysis_timestamp: str
    overall_status: str
    flagged_count: int
    total_greeks_compared: int
    greek_variances: list[dict[str, Any]]
    root_cause_summary: dict[str, Any]
    recommendations: list[str]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "analysis_timestamp": self.analysis_timestamp,
            "overall_status": self.overall_status,
            "flagged_count": self.flagged_count,
            "total_greeks_compared": self.total_greeks_compared,
            "greek_variances": self.greek_variances,
            "root_cause_summary": self.root_cause_summary,
            "recommendations": self.recommendations,
            "diagnostics": self.diagnostics,
        }


# ---------------------------------------------------------------------------
# Variance Analyzer
# ---------------------------------------------------------------------------

class GreeksVarianceAnalyzer:
    """Compare desk Greeks against VC Greeks and identify root causes.

    The analyzer:
      1. Computes absolute and relative variance for each Greek
      2. Flags variances exceeding thresholds
      3. Identifies likely root causes using heuristic rules
      4. Generates actionable recommendations
    """

    def __init__(
        self,
        thresholds: Optional[dict[str, float]] = None,
    ):
        self.thresholds = thresholds or VARIANCE_THRESHOLDS.copy()

    def analyze(
        self,
        desk_greeks: dict[str, float],
        vc_greeks: dict[str, float],
        position_id: str = "UNKNOWN",
        additional_context: Optional[dict[str, Any]] = None,
    ) -> VarianceAnalysisResult:
        """Compare desk Greeks vs VC Greeks and flag variances.

        Parameters
        ----------
        desk_greeks : dict[str, float]
            Greeks from the front-office (desk) system.
        vc_greeks : dict[str, float]
            Greeks independently computed by Valuation Control.
        position_id : str
            Identifier for the position being analyzed.
        additional_context : dict, optional
            Extra context (product type, market conditions, etc.)
            used to refine root cause identification.

        Returns
        -------
        VarianceAnalysisResult
        """
        timestamp = datetime.utcnow().isoformat() + "Z"
        context = additional_context or {}

        # Compare each Greek present in both sets
        all_greeks = set(desk_greeks.keys()) | set(vc_greeks.keys())
        greek_variances: list[GreekVariance] = []

        for greek_name in sorted(all_greeks):
            desk_val = desk_greeks.get(greek_name, 0.0)
            vc_val = vc_greeks.get(greek_name, 0.0)
            variance = self._compute_single_variance(greek_name, desk_val, vc_val)
            greek_variances.append(variance)

        # Count flagged items
        flagged = [v for v in greek_variances if v.is_flagged]
        flagged_count = len(flagged)

        # Determine overall status
        if flagged_count == 0:
            overall_status = "PASS"
        elif any(v.flag_severity == "HIGH" for v in flagged):
            overall_status = "FAIL_HIGH"
        elif any(v.flag_severity == "MEDIUM" for v in flagged):
            overall_status = "FAIL_MEDIUM"
        else:
            overall_status = "FAIL_LOW"

        # Root cause analysis
        root_cause_summary = self._identify_root_causes(
            greek_variances, context
        )

        # Generate recommendations
        recommendations = self._generate_recommendations(
            greek_variances, root_cause_summary, context
        )

        # Diagnostics
        diagnostics = {
            "thresholds_used": self.thresholds,
            "desk_greeks_provided": list(desk_greeks.keys()),
            "vc_greeks_provided": list(vc_greeks.keys()),
            "greeks_only_in_desk": sorted(
                set(desk_greeks.keys()) - set(vc_greeks.keys())
            ),
            "greeks_only_in_vc": sorted(
                set(vc_greeks.keys()) - set(desk_greeks.keys())
            ),
            "root_cause_distribution_reference": ROOT_CAUSE_DISTRIBUTION,
        }

        return VarianceAnalysisResult(
            position_id=position_id,
            analysis_timestamp=timestamp,
            overall_status=overall_status,
            flagged_count=flagged_count,
            total_greeks_compared=len(greek_variances),
            greek_variances=[v.to_dict() for v in greek_variances],
            root_cause_summary=root_cause_summary,
            recommendations=recommendations,
            diagnostics=diagnostics,
        )

    def _compute_single_variance(
        self,
        greek_name: str,
        desk_value: float,
        vc_value: float,
    ) -> GreekVariance:
        """Compute variance metrics for a single Greek."""
        absolute_variance = desk_value - vc_value

        # Relative variance: use the larger of |desk|, |vc| as denominator
        # to avoid division issues when values are near zero
        denominator = max(abs(desk_value), abs(vc_value))
        if denominator > 1e-12:
            relative_variance_pct = abs(absolute_variance) / denominator * 100.0
        else:
            # Both values are effectively zero => no meaningful variance
            relative_variance_pct = 0.0

        threshold = self.thresholds.get(greek_name, 10.0)
        is_flagged = relative_variance_pct > threshold

        # Determine severity
        if not is_flagged:
            flag_severity = "NONE"
        elif relative_variance_pct > threshold * 3:
            flag_severity = "HIGH"
        elif relative_variance_pct > threshold * 2:
            flag_severity = "MEDIUM"
        else:
            flag_severity = "LOW"

        # Identify likely root causes for this specific Greek
        likely_root_causes = self._root_causes_for_greek(
            greek_name, relative_variance_pct, desk_value, vc_value
        )

        return GreekVariance(
            greek_name=greek_name,
            desk_value=desk_value,
            vc_value=vc_value,
            absolute_variance=absolute_variance,
            relative_variance_pct=relative_variance_pct,
            threshold_pct=threshold,
            is_flagged=is_flagged,
            flag_severity=flag_severity,
            likely_root_causes=likely_root_causes,
        )

    def _root_causes_for_greek(
        self,
        greek_name: str,
        variance_pct: float,
        desk_value: float,
        vc_value: float,
    ) -> list[dict[str, Any]]:
        """Identify likely root causes for a specific Greek variance.

        Uses heuristic rules based on which Greek is affected and
        the magnitude of variance.
        """
        causes = []

        if variance_pct < 0.5:
            # Negligible variance, likely rounding
            causes.append({
                "category": RootCauseCategory.ROUNDING.value,
                "probability_pct": 90,
                "description": "Negligible variance, consistent with rounding differences",
            })
            return causes

        # Greek-specific heuristics
        if greek_name == "delta":
            causes.extend([
                {
                    "category": RootCauseCategory.MARKET_DATA_TIMING.value,
                    "probability_pct": 50,
                    "description": "Spot rate snapshot timing difference",
                },
                {
                    "category": RootCauseCategory.TRADE_POP_MISMATCH.value,
                    "probability_pct": 25,
                    "description": "Trade population or notional differences",
                },
                {
                    "category": RootCauseCategory.VOL_SURFACE_DIFF.value,
                    "probability_pct": 15,
                    "description": "Vol surface affects delta through moneyness",
                },
                {
                    "category": RootCauseCategory.CALC_METHOD.value,
                    "probability_pct": 10,
                    "description": "Delta bump size or sticky-strike vs sticky-delta",
                },
            ])
        elif greek_name == "gamma":
            causes.extend([
                {
                    "category": RootCauseCategory.CALC_METHOD.value,
                    "probability_pct": 40,
                    "description": "Gamma is highly sensitive to bump size and method",
                },
                {
                    "category": RootCauseCategory.VOL_SURFACE_DIFF.value,
                    "probability_pct": 30,
                    "description": "Vol smile curvature affects gamma significantly",
                },
                {
                    "category": RootCauseCategory.MARKET_DATA_TIMING.value,
                    "probability_pct": 20,
                    "description": "Spot level differences amplify gamma variance",
                },
                {
                    "category": RootCauseCategory.MODEL_VERSION.value,
                    "probability_pct": 10,
                    "description": "PDE grid resolution or MC paths differ",
                },
            ])
        elif greek_name == "vega":
            causes.extend([
                {
                    "category": RootCauseCategory.VOL_SURFACE_DIFF.value,
                    "probability_pct": 55,
                    "description": "Primary driver: different vol surface construction",
                },
                {
                    "category": RootCauseCategory.CALC_METHOD.value,
                    "probability_pct": 20,
                    "description": "Vol bump convention (parallel vs relative)",
                },
                {
                    "category": RootCauseCategory.MARKET_DATA_TIMING.value,
                    "probability_pct": 15,
                    "description": "Vol data timing or source differences",
                },
                {
                    "category": RootCauseCategory.MODEL_VERSION.value,
                    "probability_pct": 10,
                    "description": "SABR vs SVI or other model differences",
                },
            ])
        elif greek_name == "theta":
            causes.extend([
                {
                    "category": RootCauseCategory.CALC_METHOD.value,
                    "probability_pct": 40,
                    "description": "Day count convention or calendar differences",
                },
                {
                    "category": RootCauseCategory.MARKET_DATA_TIMING.value,
                    "probability_pct": 30,
                    "description": "Rate curve snapshot timing",
                },
                {
                    "category": RootCauseCategory.VOL_SURFACE_DIFF.value,
                    "probability_pct": 20,
                    "description": "Vol term structure roll-down differences",
                },
                {
                    "category": RootCauseCategory.ROUNDING.value,
                    "probability_pct": 10,
                    "description": "Small absolute theta values amplify relative variance",
                },
            ])
        elif greek_name == "rho":
            causes.extend([
                {
                    "category": RootCauseCategory.MARKET_DATA_TIMING.value,
                    "probability_pct": 50,
                    "description": "Yield curve snapshot timing difference",
                },
                {
                    "category": RootCauseCategory.CALC_METHOD.value,
                    "probability_pct": 25,
                    "description": "Rate bump convention (parallel vs key-rate)",
                },
                {
                    "category": RootCauseCategory.MODEL_VERSION.value,
                    "probability_pct": 15,
                    "description": "Curve construction or interpolation differences",
                },
                {
                    "category": RootCauseCategory.ROUNDING.value,
                    "probability_pct": 10,
                    "description": "Rounding in discount factor calculation",
                },
            ])
        else:
            # Generic fallback for other Greeks (vanna, volga, etc.)
            causes.extend([
                {
                    "category": RootCauseCategory.CALC_METHOD.value,
                    "probability_pct": 35,
                    "description": "Higher-order Greeks are more sensitive to method",
                },
                {
                    "category": RootCauseCategory.VOL_SURFACE_DIFF.value,
                    "probability_pct": 30,
                    "description": "Vol surface curvature affects cross-Greeks",
                },
                {
                    "category": RootCauseCategory.MARKET_DATA_TIMING.value,
                    "probability_pct": 25,
                    "description": "Market data timing affects all Greeks",
                },
                {
                    "category": RootCauseCategory.OTHER.value,
                    "probability_pct": 10,
                    "description": "Higher-order Greeks inherently less stable",
                },
            ])

        return causes

    def _identify_root_causes(
        self,
        variances: list[GreekVariance],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Aggregate root cause analysis across all Greeks.

        Examines the pattern of variances to identify the most
        likely overall root cause.
        """
        flagged = [v for v in variances if v.is_flagged]

        if not flagged:
            return {
                "primary_cause": "None — all variances within thresholds",
                "confidence": "HIGH",
                "category_probabilities": {},
                "investigation_required": False,
            }

        # Aggregate probabilities across all flagged Greeks
        category_scores: dict[str, float] = {}
        for variance in flagged:
            weight = variance.relative_variance_pct / 100.0
            for cause in variance.likely_root_causes:
                cat = cause["category"]
                prob = cause["probability_pct"] / 100.0
                category_scores[cat] = category_scores.get(cat, 0.0) + prob * weight

        # Normalize to percentages
        total_score = sum(category_scores.values())
        if total_score > 0:
            category_probabilities = {
                cat: round(score / total_score * 100, 1)
                for cat, score in sorted(
                    category_scores.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            }
        else:
            category_probabilities = {}

        # Identify primary cause
        if category_probabilities:
            primary_cause = next(iter(category_probabilities))
            primary_prob = category_probabilities[primary_cause]
        else:
            primary_cause = RootCauseCategory.OTHER.value
            primary_prob = 0.0

        # Determine confidence in root cause identification
        if primary_prob >= 50:
            confidence = "HIGH"
        elif primary_prob >= 30:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # Determine the pattern of variances for rule-based identification
        pattern_analysis = self._analyze_variance_pattern(flagged)

        return {
            "primary_cause": primary_cause,
            "primary_cause_probability_pct": primary_prob,
            "confidence": confidence,
            "category_probabilities": category_probabilities,
            "investigation_required": any(
                v.flag_severity in ("HIGH", "MEDIUM") for v in flagged
            ),
            "pattern_analysis": pattern_analysis,
            "reference_distribution": {
                cat: f"{pct * 100:.0f}%"
                for cat, pct in ROOT_CAUSE_DISTRIBUTION.items()
            },
        }

    def _analyze_variance_pattern(
        self,
        flagged_variances: list[GreekVariance],
    ) -> dict[str, Any]:
        """Analyze the pattern of flagged variances to narrow root causes."""
        pattern = {
            "flagged_greeks": [v.greek_name for v in flagged_variances],
            "all_same_direction": False,
            "vega_dominant": False,
            "gamma_dominant": False,
            "proportional_shift": False,
        }

        if not flagged_variances:
            return pattern

        # Check if all variances are in the same direction (all positive or all negative)
        signs = [
            1 if v.absolute_variance > 0 else -1
            for v in flagged_variances
            if abs(v.absolute_variance) > 1e-12
        ]
        if signs:
            pattern["all_same_direction"] = all(s == signs[0] for s in signs)

        # Check which Greeks dominate the variance
        variances_by_name = {v.greek_name: v for v in flagged_variances}

        if "vega" in variances_by_name:
            vega_var = variances_by_name["vega"].relative_variance_pct
            max_var = max(v.relative_variance_pct for v in flagged_variances)
            pattern["vega_dominant"] = vega_var >= max_var * 0.8

        if "gamma" in variances_by_name:
            gamma_var = variances_by_name["gamma"].relative_variance_pct
            max_var = max(v.relative_variance_pct for v in flagged_variances)
            pattern["gamma_dominant"] = gamma_var >= max_var * 0.8

        # Check for proportional shift (suggests trade pop mismatch)
        if len(flagged_variances) >= 3:
            rel_vars = [v.relative_variance_pct for v in flagged_variances]
            avg_var = sum(rel_vars) / len(rel_vars)
            if avg_var > 0:
                dispersion = sum(
                    abs(rv - avg_var) / avg_var for rv in rel_vars
                ) / len(rel_vars)
                pattern["proportional_shift"] = dispersion < 0.3

        return pattern

    def _generate_recommendations(
        self,
        variances: list[GreekVariance],
        root_cause_summary: dict[str, Any],
        context: dict[str, Any],
    ) -> list[str]:
        """Generate actionable recommendations based on variance analysis."""
        recommendations = []
        flagged = [v for v in variances if v.is_flagged]

        if not flagged:
            recommendations.append(
                "All Greek variances within thresholds. No action required."
            )
            return recommendations

        primary_cause = root_cause_summary.get("primary_cause", "")

        # Cause-specific recommendations
        if primary_cause == RootCauseCategory.MARKET_DATA_TIMING.value:
            recommendations.extend([
                "Verify market data snapshot timestamps between desk and VC systems.",
                "Align EOD market data cut-off time (recommend London 4pm or NY 5pm).",
                "Check for stale quotes in either system.",
            ])
        elif primary_cause == RootCauseCategory.VOL_SURFACE_DIFF.value:
            recommendations.extend([
                "Compare vol surface construction methods (SABR params, smile fitting).",
                "Verify vol data sources are identical.",
                "Check for differences in ATM convention (delta-neutral vs forward).",
            ])
        elif primary_cause == RootCauseCategory.TRADE_POP_MISMATCH.value:
            recommendations.extend([
                "Reconcile trade populations between desk and VC systems.",
                "Check for late bookings, cancelled trades, or amendments.",
                "Verify notional amounts and trade dates match.",
            ])
        elif primary_cause == RootCauseCategory.CALC_METHOD.value:
            recommendations.extend([
                "Align Greek bump sizes (delta: 1%, gamma: 1%, vega: 1 vol pt).",
                "Verify finite-difference scheme (central vs forward difference).",
                "Check day-count and calendar conventions for theta.",
            ])
        elif primary_cause == RootCauseCategory.MODEL_VERSION.value:
            recommendations.extend([
                "Verify both systems are on the same model version.",
                "Check for recent model updates or parameter recalibrations.",
                "Ensure PDE grid resolution and MC path counts are aligned.",
            ])

        # Severity-based recommendations
        high_severity = [v for v in flagged if v.flag_severity == "HIGH"]
        if high_severity:
            greek_names = ", ".join(v.greek_name for v in high_severity)
            recommendations.append(
                f"URGENT: High-severity variances detected in {greek_names}. "
                f"Escalate to VC manager for immediate investigation."
            )

        # Add generic recommendation for investigation
        if root_cause_summary.get("investigation_required"):
            recommendations.append(
                "Schedule a joint desk/VC meeting to resolve flagged variances "
                "before next EOD reporting cycle."
            )

        return recommendations
