"""Focused API tests that require no live infrastructure."""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from serving.app.api import create_app
from serving.app.config import Settings
from serving.app.model_loader import ModelLoadError, PredictionModel
from serving.app.schemas import MODEL_FEATURE_COLUMNS

LOGGER = logging.getLogger(__name__)


class FakePriceModel:
    """Capture model input and return a deterministic prediction."""

    def __init__(self, predicted_price: float = 175.25) -> None:
        """Store the prediction returned by the test double."""
        self.predicted_price = predicted_price
        self.received: pd.DataFrame | None = None

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Capture the exact frame supplied by the transport layer."""
        self.received = features.copy()
        return np.array([self.predicted_price])


@pytest.fixture
def listing_payload() -> dict[str, object]:
    """Return one request matching the fitted estimator contract."""
    return {
        "neighbourhood_group": "Manhattan",
        "neighbourhood": "Midtown",
        "latitude": 40.758,
        "longitude": -73.9855,
        "room_type": "Entire home/apt",
        "minimum_nights": 2,
        "number_of_reviews": 10,
        "reviews_per_month": 1.25,
        "calculated_host_listings_count": 1,
        "availability_365": 120,
        "has_reviews": 1,
        "days_since_last_review": 30,
        "minimum_nights_band": "short",
        "availability_band": "medium",
        "location_cell": "40.76_-73.99",
        "distance_to_midtown_km": 0.0,
    }


@pytest.fixture
def fake_model() -> FakePriceModel:
    """Return a deterministic in-memory prediction model."""
    return FakePriceModel()


@pytest.fixture
def settings() -> Settings:
    """Return isolated runtime settings for tests."""
    return Settings(
        MLFLOW_TRACKING_URI="http://mlflow.test:5000",
        MODEL_NAME="test-airbnb-model",
        MODEL_ALIAS="candidate",
        LOG_LEVEL="WARNING",
    )


def successful_loader(model: PredictionModel) -> Callable[[Settings], PredictionModel]:
    """Return a loader callback that exposes the supplied model."""

    def load(settings: Settings) -> PredictionModel:
        """Return the fixed model without accessing MLflow."""
        del settings
        return model

    return load


def test_health_does_not_execute_inference(
    fake_model: FakePriceModel, settings: Settings
) -> None:
    """Return process health without making a prediction."""
    app = create_app(settings=settings, model_loader=successful_loader(fake_model))
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_model.received is None


def test_ready_identifies_loaded_alias(
    fake_model: FakePriceModel, settings: Settings
) -> None:
    """Report configured model identity after successful startup."""
    app = create_app(settings=settings, model_loader=successful_loader(fake_model))
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "model": "test-airbnb-model",
        "alias": "candidate",
    }


def test_startup_failure_leaves_service_not_ready(settings: Settings) -> None:
    """Keep liveness available while returning 503 when registry loading fails."""

    def unavailable_loader(settings: Settings) -> PredictionModel:
        """Simulate an unavailable registry alias during startup."""
        del settings
        raise ModelLoadError("registry unavailable")

    app = create_app(settings=settings, model_loader=unavailable_loader)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Champion model is not ready"}


def test_predict_validates_request_schema(
    fake_model: FakePriceModel,
    settings: Settings,
    listing_payload: dict[str, object],
) -> None:
    """Reject missing, invalid, and unexpected fitted features."""
    app = create_app(settings=settings, model_loader=successful_loader(fake_model))
    missing = {key: value for key, value in listing_payload.items() if key != "room_type"}
    invalid = {**listing_payload, "availability_365": 366}
    extra = {**listing_payload, "bedrooms": 2}
    with TestClient(app) as client:
        assert client.post("/predict", json=missing).status_code == 422
        assert client.post("/predict", json=invalid).status_code == 422
        assert client.post("/predict", json=extra).status_code == 422


def test_predict_preserves_order_and_response_schema(
    fake_model: FakePriceModel,
    settings: Settings,
    listing_payload: dict[str, object],
) -> None:
    """Preserve feature ordering and return model identity with the price."""
    app = create_app(settings=settings, model_loader=successful_loader(fake_model))
    with TestClient(app) as client:
        response = client.post("/predict", json=listing_payload)
    assert response.status_code == 200
    assert response.json() == {
        "predicted_price": 175.25,
        "model_name": "test-airbnb-model",
        "model_alias": "candidate",
    }
    assert fake_model.received is not None
    assert tuple(fake_model.received.columns) == MODEL_FEATURE_COLUMNS
    assert fake_model.received.shape == (1, len(MODEL_FEATURE_COLUMNS))
