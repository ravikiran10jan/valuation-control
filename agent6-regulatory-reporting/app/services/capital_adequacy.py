"""Capital Adequacy Calculator — Basel III CET1, RWA, and Capital Ratios.

Implements the full Capital_Adequacy sheet from the Excel model:

CET1 Capital Calculation:
  Shareholders Equity: $50,000,000
  + Retained Earnings: $25,000,000
  + AOCI: $2,000,000
  - Goodwill & Intangibles: -$5,000,000
  - Deferred Tax Assets: -$1,000,000
  - AVA Deduction (Level 3): -$34,425 (from AVA calc)
  - Other Regulatory Deductions: -$500,000
  = TOTAL CET1 = $70,465,575

RWA Calculation:
  Credit Risk:
    Corporate: $150M x 100% = $150,000,000
    Bank: $75M x 50% = $37,500,000
    Retail: $50M x 75% = $37,500,000
    Total Credit RWA = $225,000,000

  Market Risk:
    FX: $485.75M x 8% = $38,860,000
    IR: $25M x 6% = $1,500,000
    Equity: $10M x 25% = $2,500,000
    Total Market RWA = $42,860,000

  Operational Risk:
    Gross Income $200M x 15% (BIA) = $30,000,000

  TOTAL RWA = $297,860,000

Capital Ratios:
  CET1 Ratio = CET1/RWA = 23.7% (approx)
  Min required: 4.5%
  With CCB: 7.0%
  With CCyB: 7.5%
  Leverage Ratio = CET1/Total Exposure
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.postgres import CapitalAdequacyReport, RegulatoryReport
from app.models.schemas import (
    CapitalAdequacyRequest,
    CapitalAdequacyResult,
    CapitalRatios,
    CET1CapitalComponents,
    CreditRiskRWA,
    MarketRiskRWA,
    OperationalRiskRWA,
    ReportStatus,
    RWAComponents,
)

log = structlog.get_logger()

# Basel III standard risk weights
_CREDIT_WEIGHTS = {
    "corporate": Decimal("1.00"),   # 100%
    "bank": Decimal("0.50"),         # 50%
    "retail": Decimal("0.75"),       # 75%
}

_MARKET_WEIGHTS = {
    "fx": Decimal("0.08"),           # 8%
    "ir": Decimal("0.06"),           # 6%
    "equity": Decimal("0.25"),       # 25%
}

_BIA_FACTOR = Decimal("0.15")  # Basic Indicator Approach: 15%

# Regulatory minimums
_CET1_MINIMUM = Decimal("0.045")     # 4.5%
_CET1_WITH_CCB = Decimal("0.070")    # 7.0% (4.5% + 2.5% CCB)
_CET1_WITH_CCYB = Decimal("0.075")   # 7.5% (4.5% + 2.5% CCB + 0.5% CCyB example)
_LEVERAGE_MINIMUM = Decimal("0.03")   # 3.0%


def _round2(value: Decimal) -> Decimal:
    """Round to 2 decimal places."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _round6(value: Decimal) -> Decimal:
    """Round to 6 decimal places for ratio precision."""
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _calculate_cet1(
    shareholders_equity: Decimal,
    retained_earnings: Decimal,
    aoci: Decimal,
    goodwill_intangibles: Decimal,
    deferred_tax_assets: Decimal,
    ava_deduction: Decimal,
    other_regulatory_deductions: Decimal,
) -> CET1CapitalComponents:
    """Calculate CET1 capital from components.

    Formula:
      CET1 = Shareholders Equity + Retained Earnings + AOCI
             - Goodwill & Intangibles
             - Deferred Tax Assets
             - AVA Deduction (Level 3)
             - Other Regulatory Deductions

    Excel example:
      $50M + $25M + $2M - $5M - $1M - $34,425 - $500K = $70,465,575
    """
    total_cet1 = (
        shareholders_equity
        + retained_earnings
        + aoci
        - goodwill_intangibles
        - deferred_tax_assets
        - ava_deduction
        - other_regulatory_deductions
    )

    return CET1CapitalComponents(
        shareholders_equity=_round2(shareholders_equity),
        retained_earnings=_round2(retained_earnings),
        aoci=_round2(aoci),
        goodwill_intangibles=_round2(goodwill_intangibles),
        deferred_tax_assets=_round2(deferred_tax_assets),
        ava_deduction=_round2(ava_deduction),
        other_regulatory_deductions=_round2(other_regulatory_deductions),
        total_cet1=_round2(total_cet1),
    )


def _calculate_credit_risk_rwa(
    corporate_exposure: Decimal,
    bank_exposure: Decimal,
    retail_exposure: Decimal,
) -> CreditRiskRWA:
    """Calculate credit risk RWA using standardized approach.

    Excel example:
      Corporate: $150M x 100% = $150,000,000
      Bank: $75M x 50% = $37,500,000
      Retail: $50M x 75% = $37,500,000
      Total = $225,000,000
    """
    corp_weight = _CREDIT_WEIGHTS["corporate"]
    bank_weight = _CREDIT_WEIGHTS["bank"]
    retail_weight = _CREDIT_WEIGHTS["retail"]

    corporate_rwa = corporate_exposure * corp_weight
    bank_rwa = bank_exposure * bank_weight
    retail_rwa = retail_exposure * retail_weight
    total = corporate_rwa + bank_rwa + retail_rwa

    return CreditRiskRWA(
        corporate_exposure=_round2(corporate_exposure),
        corporate_weight=corp_weight,
        corporate_rwa=_round2(corporate_rwa),
        bank_exposure=_round2(bank_exposure),
        bank_weight=bank_weight,
        bank_rwa=_round2(bank_rwa),
        retail_exposure=_round2(retail_exposure),
        retail_weight=retail_weight,
        retail_rwa=_round2(retail_rwa),
        total_credit_rwa=_round2(total),
    )


def _calculate_market_risk_rwa(
    fx_exposure: Decimal,
    ir_exposure: Decimal,
    equity_exposure: Decimal,
) -> MarketRiskRWA:
    """Calculate market risk RWA.

    Excel example:
      FX: $485.75M x 8% = $38,860,000
      IR: $25M x 6% = $1,500,000
      Equity: $10M x 25% = $2,500,000
      Total = $42,860,000
    """
    fx_weight = _MARKET_WEIGHTS["fx"]
    ir_weight = _MARKET_WEIGHTS["ir"]
    equity_weight = _MARKET_WEIGHTS["equity"]

    fx_rwa = fx_exposure * fx_weight
    ir_rwa = ir_exposure * ir_weight
    equity_rwa = equity_exposure * equity_weight
    total = fx_rwa + ir_rwa + equity_rwa

    return MarketRiskRWA(
        fx_exposure=_round2(fx_exposure),
        fx_weight=fx_weight,
        fx_rwa=_round2(fx_rwa),
        ir_exposure=_round2(ir_exposure),
        ir_weight=ir_weight,
        ir_rwa=_round2(ir_rwa),
        equity_exposure=_round2(equity_exposure),
        equity_weight=equity_weight,
        equity_rwa=_round2(equity_rwa),
        total_market_rwa=_round2(total),
    )


def _calculate_operational_risk_rwa(
    gross_income: Decimal,
) -> OperationalRiskRWA:
    """Calculate operational risk RWA using Basic Indicator Approach (BIA).

    Excel example:
      $200M x 15% = $30,000,000
    """
    total = gross_income * _BIA_FACTOR

    return OperationalRiskRWA(
        gross_income=_round2(gross_income),
        bia_factor=_BIA_FACTOR,
        total_operational_rwa=_round2(total),
    )


def _calculate_capital_ratios(
    total_cet1: Decimal,
    total_rwa: Decimal,
    total_exposure: Decimal | None = None,
) -> CapitalRatios:
    """Calculate capital adequacy ratios and compare to regulatory minimums.

    Excel example:
      CET1 Ratio = $70,465,575 / $297,860,000 = 23.66%
      Min required: 4.5% -> PASS
      With CCB: 7.0% -> PASS
      With CCyB: 7.5% -> PASS
    """
    if total_rwa == 0:
        cet1_ratio = Decimal(0)
    else:
        cet1_ratio = total_cet1 / total_rwa

    leverage_ratio = None
    if total_exposure and total_exposure > 0:
        leverage_ratio = total_cet1 / total_exposure

    cet1_surplus = cet1_ratio - _CET1_MINIMUM
    cet1_surplus_with_buffers = cet1_ratio - _CET1_WITH_CCYB

    return CapitalRatios(
        cet1_ratio=_round6(cet1_ratio),
        cet1_minimum=_CET1_MINIMUM,
        cet1_with_ccb=_CET1_WITH_CCB,
        cet1_with_ccyb=_CET1_WITH_CCYB,
        leverage_ratio=_round6(leverage_ratio) if leverage_ratio else None,
        leverage_minimum=_LEVERAGE_MINIMUM,
        cet1_surplus=_round6(cet1_surplus),
        cet1_surplus_with_buffers=_round6(cet1_surplus_with_buffers),
        passes_minimum=cet1_ratio >= _CET1_MINIMUM,
        passes_with_ccb=cet1_ratio >= _CET1_WITH_CCB,
        passes_with_ccyb=cet1_ratio >= _CET1_WITH_CCYB,
    )


class CapitalAdequacyService:
    """Service for computing and persisting capital adequacy reports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_capital_adequacy(
        self,
        request: CapitalAdequacyRequest,
    ) -> CapitalAdequacyResult:
        """Calculate full capital adequacy report matching Excel Capital_Adequacy sheet.

        Steps:
          1. Calculate CET1 capital from equity components and deductions
          2. Calculate RWA across credit, market, and operational risk
          3. Compute capital ratios and compare to regulatory minimums
          4. Persist the report for audit trail

        Returns CapitalAdequacyResult with all components, breakdowns, and ratios.
        """
        reporting_date = request.reporting_date

        # Determine AVA deduction
        ava_deduction = request.ava_deduction or Decimal(0)

        # Step 1: CET1 Capital
        cet1_components = _calculate_cet1(
            shareholders_equity=request.shareholders_equity,
            retained_earnings=request.retained_earnings,
            aoci=request.aoci,
            goodwill_intangibles=request.goodwill_intangibles,
            deferred_tax_assets=request.deferred_tax_assets,
            ava_deduction=ava_deduction,
            other_regulatory_deductions=request.other_regulatory_deductions,
        )

        # Step 2: RWA Components
        credit_risk = _calculate_credit_risk_rwa(
            corporate_exposure=request.corporate_exposure,
            bank_exposure=request.bank_exposure,
            retail_exposure=request.retail_exposure,
        )

        market_risk = _calculate_market_risk_rwa(
            fx_exposure=request.fx_exposure,
            ir_exposure=request.ir_exposure,
            equity_exposure=request.equity_exposure,
        )

        operational_risk = _calculate_operational_risk_rwa(
            gross_income=request.gross_income,
        )

        total_rwa = (
            credit_risk.total_credit_rwa
            + market_risk.total_market_rwa
            + operational_risk.total_operational_rwa
        )

        rwa_components = RWAComponents(
            credit_risk=credit_risk,
            market_risk=market_risk,
            operational_risk=operational_risk,
            total_rwa=_round2(total_rwa),
        )

        # Step 3: Capital Ratios
        capital_ratios = _calculate_capital_ratios(
            total_cet1=cet1_components.total_cet1,
            total_rwa=total_rwa,
            total_exposure=request.total_exposure,
        )

        # CET1 ratio as percentage for display
        cet1_ratio_pct = _round2(capital_ratios.cet1_ratio * Decimal("100"))

        # Step 4: Persist report
        report_row = CapitalAdequacyReport(
            reporting_date=reporting_date,
            status="DRAFT",
            shareholders_equity=float(request.shareholders_equity),
            retained_earnings=float(request.retained_earnings),
            aoci=float(request.aoci),
            goodwill_intangibles=float(request.goodwill_intangibles),
            deferred_tax_assets=float(request.deferred_tax_assets),
            ava_deduction=float(ava_deduction),
            other_regulatory_deductions=float(request.other_regulatory_deductions),
            total_cet1=float(cet1_components.total_cet1),
            credit_risk_rwa=float(credit_risk.total_credit_rwa),
            market_risk_rwa=float(market_risk.total_market_rwa),
            operational_risk_rwa=float(operational_risk.total_operational_rwa),
            total_rwa=float(total_rwa),
            cet1_ratio=float(capital_ratios.cet1_ratio),
            leverage_ratio=float(capital_ratios.leverage_ratio) if capital_ratios.leverage_ratio else None,
            full_breakdown={
                "cet1_components": {
                    "shareholders_equity": float(request.shareholders_equity),
                    "retained_earnings": float(request.retained_earnings),
                    "aoci": float(request.aoci),
                    "goodwill_intangibles": float(request.goodwill_intangibles),
                    "deferred_tax_assets": float(request.deferred_tax_assets),
                    "ava_deduction": float(ava_deduction),
                    "other_regulatory_deductions": float(request.other_regulatory_deductions),
                    "total_cet1": float(cet1_components.total_cet1),
                },
                "rwa_components": {
                    "credit_risk": {
                        "corporate": {"exposure": float(request.corporate_exposure), "weight": 1.00, "rwa": float(credit_risk.corporate_rwa)},
                        "bank": {"exposure": float(request.bank_exposure), "weight": 0.50, "rwa": float(credit_risk.bank_rwa)},
                        "retail": {"exposure": float(request.retail_exposure), "weight": 0.75, "rwa": float(credit_risk.retail_rwa)},
                        "total": float(credit_risk.total_credit_rwa),
                    },
                    "market_risk": {
                        "fx": {"exposure": float(request.fx_exposure), "weight": 0.08, "rwa": float(market_risk.fx_rwa)},
                        "ir": {"exposure": float(request.ir_exposure), "weight": 0.06, "rwa": float(market_risk.ir_rwa)},
                        "equity": {"exposure": float(request.equity_exposure), "weight": 0.25, "rwa": float(market_risk.equity_rwa)},
                        "total": float(market_risk.total_market_rwa),
                    },
                    "operational_risk": {
                        "gross_income": float(request.gross_income),
                        "bia_factor": 0.15,
                        "total": float(operational_risk.total_operational_rwa),
                    },
                    "total_rwa": float(total_rwa),
                },
                "capital_ratios": {
                    "cet1_ratio": float(capital_ratios.cet1_ratio),
                    "cet1_ratio_pct": float(cet1_ratio_pct),
                    "cet1_minimum": float(_CET1_MINIMUM),
                    "cet1_with_ccb": float(_CET1_WITH_CCB),
                    "cet1_with_ccyb": float(_CET1_WITH_CCYB),
                    "passes_minimum": capital_ratios.passes_minimum,
                    "passes_with_ccb": capital_ratios.passes_with_ccb,
                    "passes_with_ccyb": capital_ratios.passes_with_ccyb,
                    "leverage_ratio": float(capital_ratios.leverage_ratio) if capital_ratios.leverage_ratio else None,
                },
            },
        )
        self.db.add(report_row)

        # Also persist to the general regulatory_reports table
        reg_report = RegulatoryReport(
            report_type="CAPITAL_ADEQUACY",
            reporting_date=reporting_date,
            firm_reference=settings.firm_reference_uk,
            status="DRAFT",
            content=report_row.full_breakdown,
            file_format="JSON",
        )
        self.db.add(reg_report)

        await self.db.flush()

        log.info(
            "capital_adequacy_calculated",
            reporting_date=str(reporting_date),
            total_cet1=float(cet1_components.total_cet1),
            total_rwa=float(total_rwa),
            cet1_ratio_pct=float(cet1_ratio_pct),
            passes_minimum=capital_ratios.passes_minimum,
            passes_with_buffers=capital_ratios.passes_with_ccyb,
            report_id=report_row.report_id,
        )

        return CapitalAdequacyResult(
            report_id=report_row.report_id,
            reporting_date=reporting_date,
            status=ReportStatus.DRAFT,
            cet1_components=cet1_components,
            rwa_components=rwa_components,
            capital_ratios=capital_ratios,
            total_cet1=cet1_components.total_cet1,
            total_rwa=_round2(total_rwa),
            cet1_ratio_pct=cet1_ratio_pct,
            generated_at=datetime.utcnow(),
        )

    async def get_latest_report(
        self,
        reporting_date: date | None = None,
    ) -> CapitalAdequacyResult | None:
        """Retrieve the latest capital adequacy report.

        If reporting_date is provided, returns the report for that date.
        Otherwise returns the most recent report.
        """
        stmt = select(CapitalAdequacyReport)

        if reporting_date:
            stmt = stmt.where(CapitalAdequacyReport.reporting_date == reporting_date)

        stmt = stmt.order_by(CapitalAdequacyReport.generated_at.desc()).limit(1)

        result = await self.db.execute(stmt)
        report = result.scalar_one_or_none()

        if not report:
            return None

        # Reconstruct the result from stored data
        breakdown = report.full_breakdown or {}
        cet1_data = breakdown.get("cet1_components", {})
        rwa_data = breakdown.get("rwa_components", {})
        ratios_data = breakdown.get("capital_ratios", {})

        credit_data = rwa_data.get("credit_risk", {})
        market_data = rwa_data.get("market_risk", {})
        op_data = rwa_data.get("operational_risk", {})

        cet1_components = CET1CapitalComponents(
            shareholders_equity=Decimal(str(cet1_data.get("shareholders_equity", 0))),
            retained_earnings=Decimal(str(cet1_data.get("retained_earnings", 0))),
            aoci=Decimal(str(cet1_data.get("aoci", 0))),
            goodwill_intangibles=Decimal(str(cet1_data.get("goodwill_intangibles", 0))),
            deferred_tax_assets=Decimal(str(cet1_data.get("deferred_tax_assets", 0))),
            ava_deduction=Decimal(str(cet1_data.get("ava_deduction", 0))),
            other_regulatory_deductions=Decimal(str(cet1_data.get("other_regulatory_deductions", 0))),
            total_cet1=Decimal(str(report.total_cet1)),
        )

        credit_risk = CreditRiskRWA(
            corporate_exposure=Decimal(str(credit_data.get("corporate", {}).get("exposure", 0))),
            corporate_weight=Decimal("1.00"),
            corporate_rwa=Decimal(str(credit_data.get("corporate", {}).get("rwa", 0))),
            bank_exposure=Decimal(str(credit_data.get("bank", {}).get("exposure", 0))),
            bank_weight=Decimal("0.50"),
            bank_rwa=Decimal(str(credit_data.get("bank", {}).get("rwa", 0))),
            retail_exposure=Decimal(str(credit_data.get("retail", {}).get("exposure", 0))),
            retail_weight=Decimal("0.75"),
            retail_rwa=Decimal(str(credit_data.get("retail", {}).get("rwa", 0))),
            total_credit_rwa=Decimal(str(report.credit_risk_rwa)),
        )

        market_risk = MarketRiskRWA(
            fx_exposure=Decimal(str(market_data.get("fx", {}).get("exposure", 0))),
            fx_weight=Decimal("0.08"),
            fx_rwa=Decimal(str(market_data.get("fx", {}).get("rwa", 0))),
            ir_exposure=Decimal(str(market_data.get("ir", {}).get("exposure", 0))),
            ir_weight=Decimal("0.06"),
            ir_rwa=Decimal(str(market_data.get("ir", {}).get("rwa", 0))),
            equity_exposure=Decimal(str(market_data.get("equity", {}).get("exposure", 0))),
            equity_weight=Decimal("0.25"),
            equity_rwa=Decimal(str(market_data.get("equity", {}).get("rwa", 0))),
            total_market_rwa=Decimal(str(report.market_risk_rwa)),
        )

        operational_risk = OperationalRiskRWA(
            gross_income=Decimal(str(op_data.get("gross_income", 0))),
            bia_factor=Decimal("0.15"),
            total_operational_rwa=Decimal(str(report.operational_risk_rwa)),
        )

        total_rwa = Decimal(str(report.total_rwa))
        rwa_components = RWAComponents(
            credit_risk=credit_risk,
            market_risk=market_risk,
            operational_risk=operational_risk,
            total_rwa=total_rwa,
        )

        cet1_ratio = Decimal(str(report.cet1_ratio))
        leverage_ratio_val = Decimal(str(report.leverage_ratio)) if report.leverage_ratio else None

        capital_ratios = CapitalRatios(
            cet1_ratio=cet1_ratio,
            cet1_minimum=_CET1_MINIMUM,
            cet1_with_ccb=_CET1_WITH_CCB,
            cet1_with_ccyb=_CET1_WITH_CCYB,
            leverage_ratio=leverage_ratio_val,
            leverage_minimum=_LEVERAGE_MINIMUM,
            cet1_surplus=cet1_ratio - _CET1_MINIMUM,
            cet1_surplus_with_buffers=cet1_ratio - _CET1_WITH_CCYB,
            passes_minimum=cet1_ratio >= _CET1_MINIMUM,
            passes_with_ccb=cet1_ratio >= _CET1_WITH_CCB,
            passes_with_ccyb=cet1_ratio >= _CET1_WITH_CCYB,
        )

        cet1_ratio_pct = _round2(cet1_ratio * Decimal("100"))

        return CapitalAdequacyResult(
            report_id=report.report_id,
            reporting_date=report.reporting_date,
            status=ReportStatus(report.status),
            cet1_components=cet1_components,
            rwa_components=rwa_components,
            capital_ratios=capital_ratios,
            total_cet1=Decimal(str(report.total_cet1)),
            total_rwa=total_rwa,
            cet1_ratio_pct=cet1_ratio_pct,
            generated_at=report.generated_at,
        )
