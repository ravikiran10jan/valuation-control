"""Tests for the FastAPI routes."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestFXBarrierEndpoint:
    def test_price_fx_barrier(self):
        payload = {
            "spot": 1.10,
            "lower_barrier": 1.05,
            "upper_barrier": 1.15,
            "maturity": 0.5,
            "notional": 1_000_000,
            "vol": 0.10,
            "r_dom": 0.05,
            "r_for": 0.03,
            "barrier_type": "DNT",
            "mc_paths": 5000,
        }
        resp = client.post("/pricing/fx-barrier", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["fair_value"] > 0
        assert "analytical" in data["methods"]
        assert "monte_carlo" in data["methods"]

    def test_invalid_barriers(self):
        payload = {
            "spot": 1.20,
            "lower_barrier": 1.05,
            "upper_barrier": 1.15,
            "maturity": 0.5,
            "notional": 1e6,
            "vol": 0.10,
            "r_dom": 0.05,
            "r_for": 0.03,
        }
        resp = client.post("/pricing/fx-barrier", json=payload)
        assert resp.status_code == 422


class TestEquityOptionEndpoint:
    def test_price_call(self):
        payload = {
            "spot": 100,
            "strike": 100,
            "maturity": 1.0,
            "vol": 0.20,
            "r_dom": 0.05,
            "option_type": "call",
            "exercise_style": "european",
        }
        resp = client.post("/pricing/equity-option", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["fair_value"] > 0
        assert "black_scholes" in data["methods"]


class TestDistressedLoanEndpoint:
    def test_price_loan(self):
        payload = {
            "notional": 100_000_000,
            "collateral": {"inventory": 50_000_000, "ppe": 30_000_000},
            "financials": {"ebitda": 20_000_000, "total_debt": 120_000_000},
        }
        resp = client.post("/pricing/distressed-loan", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["fair_value"] > 0


class TestCommoditiesBasketEndpoint:
    def test_price_basket(self):
        payload = {
            "asset_names": ["WTI", "Gold"],
            "spots": [73.50, 2065],
            "vols": [0.285, 0.162],
            "drifts": [0.03, 0.02],
            "correlation_matrix": [[1.0, 0.15], [0.15, 1.0]],
            "barriers": [55.0, 1800.0],
            "maturity": 1.0,
            "notional": 1_000_000,
            "mc_paths": 5000,
        }
        resp = client.post("/pricing/commodities-basket", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["fair_value"] >= 0


class TestBermudanSwaptionEndpoint:
    def test_price_swaption(self):
        payload = {
            "notional": 10_000_000,
            "fixed_rate": 0.047,
            "exercise_dates_years": [1.0, 2.0, 3.0],
            "swap_tenor": 5.0,
            "yield_curve": [[1.0, 0.04], [5.0, 0.045], [10.0, 0.05], [20.0, 0.052]],
            "kappa": 0.03,
            "sigma": 0.01,
        }
        resp = client.post("/pricing/bermudan-swaption", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["fair_value"] >= 0


class TestVolSurfaceEndpoint:
    def test_interpolate(self):
        payload = {
            "deltas": [0.10, 0.25, 0.50, 0.75, 0.90],
            "vols": [0.195, 0.185, 0.178, 0.172, 0.168],
            "forward": 1.10,
            "maturity": 0.5,
        }
        resp = client.post("/pricing/vol-surface", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "cubic_spline" in data
        assert "sabr" in data


class TestValidationEndpoint:
    def test_validate_equity(self):
        payload = {
            "model_name": "equity_option",
            "position": {
                "spot": 100,
                "strike": 100,
                "maturity": 1.0,
                "vol": 0.20,
                "r_dom": 0.05,
            },
        }
        resp = client.post("/pricing/validate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "VALIDATED"

    def test_unknown_model(self):
        payload = {"model_name": "nonexistent", "position": {}}
        resp = client.post("/pricing/validate", json=payload)
        assert resp.status_code == 400
