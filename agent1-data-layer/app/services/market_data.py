"""Market data service -- orchestrates connectors, validation, and persistence."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import structlog

from app.connectors.base import MarketDataConnector
from app.connectors.factory import get_primary_connector, get_secondary_connector
from app.models import mongo as mongo_repo
from app.services.validation import DataValidator, ValidationReport

log = structlog.get_logger()


class MarketDataService:
    def __init__(self) -> None:
        self._primary: MarketDataConnector = get_primary_connector()
        self._secondary: Optional[MarketDataConnector] = get_secondary_connector()
        self._validator = DataValidator()

    async def get_spot(
        self, currency_pair: str, as_of: Optional[date] = None
    ) -> dict:
        primary_data = await self._primary.get_spot(currency_pair, as_of)

        secondary_value = None
        if self._secondary:
            try:
                sec = await self._secondary.get_spot(currency_pair, as_of)
                secondary_value = sec["value"]
            except Exception:
                log.warning("secondary_spot_failed", pair=currency_pair)

        report = self._validator.validate_market_data(
            field_name=f"{currency_pair}_Spot",
            value=primary_data["value"],
            timestamp=datetime.fromisoformat(primary_data["timestamp"]),
            secondary_value=secondary_value,
        )

        # Persist to MongoDB for historical tracking
        await mongo_repo.insert_market_data_point(
            field=f"{currency_pair}_Spot",
            value=primary_data["value"],
            as_of=as_of or date.today(),
            source=primary_data["source"],
        )

        return {
            **primary_data,
            "currency_pair": currency_pair,
            "validation": {
                "passed": report.passed,
                "failures": [f.message for f in report.failures],
            },
        }

    async def get_vol_surface(
        self, currency_pair: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        data = await self._primary.get_vol_surface(currency_pair, tenor, as_of)

        report = self._validator.validate_vol_surface(
            currency_pair, tenor, {"25P": data["25P"], "ATM": data["ATM"], "25C": data["25C"]}
        )

        # Persist each delta point
        effective_date = as_of or date.today()
        for delta_label in ("25P", "ATM", "25C"):
            await mongo_repo.insert_vol_surface_point(
                currency_pair=currency_pair,
                tenor=tenor,
                delta=delta_label,
                volatility=data[delta_label],
                as_of=effective_date,
                source=data["source"],
            )

        return {
            "currency_pair": currency_pair,
            "tenor": tenor,
            "points": [
                {"delta": "25P", "volatility": data["25P"]},
                {"delta": "ATM", "volatility": data["ATM"]},
                {"delta": "25C", "volatility": data["25C"]},
            ],
            "source": data["source"],
            "timestamp": data["timestamp"],
            "validation": {
                "passed": report.passed,
                "failures": [f.message for f in report.failures],
            },
        }

    async def get_yield_curve(
        self, curve_name: str, as_of: Optional[date] = None
    ) -> dict:
        data = await self._primary.get_yield_curve(curve_name, as_of)

        report = self._validator.validate_yield_curve(curve_name, data["tenors"])

        effective_date = as_of or date.today()
        for tenor, rate in data["tenors"].items():
            await mongo_repo.insert_market_data_point(
                field=f"{curve_name}_{tenor}",
                value=rate,
                as_of=effective_date,
                source=data["source"],
            )

        return {
            "curve_name": curve_name,
            **data,
            "validation": {
                "passed": report.passed,
                "failures": [f.message for f in report.failures],
            },
        }

    async def get_cds_spread(
        self, reference_entity: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        data = await self._primary.get_cds_spread(reference_entity, tenor, as_of)

        await mongo_repo.insert_market_data_point(
            field=f"{reference_entity}_{tenor}_CDS",
            value=data["spread_bps"],
            as_of=as_of or date.today(),
            source=data["source"],
        )

        return {"reference_entity": reference_entity, "tenor": tenor, **data}

    async def get_forward_points(
        self, currency_pair: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        data = await self._primary.get_forward_points(currency_pair, tenor, as_of)

        await mongo_repo.insert_market_data_point(
            field=f"{currency_pair}_{tenor}_FWD",
            value=data["points"],
            as_of=as_of or date.today(),
            source=data["source"],
        )

        return {"currency_pair": currency_pair, "tenor": tenor, **data}

    async def health(self) -> dict:
        primary_ok = await self._primary.health_check()
        secondary_ok = (
            await self._secondary.health_check() if self._secondary else None
        )
        return {
            "primary": {"healthy": primary_ok, "type": type(self._primary).__name__},
            "secondary": (
                {"healthy": secondary_ok, "type": type(self._secondary).__name__}
                if self._secondary
                else None
            ),
        }
