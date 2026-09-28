"""Serve one-listing predictions from the MLflow Registry champion."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, Request

from serving.app.config import Settings, get_settings
from serving.app.model_loader import (
    ModelLoadError,
    PredictionModel,
    load_champion_model,
)
from serving.app.schemas import (
    HealthResponse,
    ListingFeatures,
    PredictionResponse,
    ReadinessResponse,
)

LOGGER = logging.getLogger(__name__)
SAFE_LOAD_ERROR = "Champion model is not ready"
SAFE_PREDICTION_ERROR = "Prediction failed"
ModelLoader = Callable[[Settings], PredictionModel]


def create_app(
    *,
    settings: Settings | None = None,
    model_loader: ModelLoader = load_champion_model,
) -> FastAPI:
    """Create an application whose model is loaded once during startup."""
    runtime_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Load the aliased model once and retain clean not-ready state on failure."""
        logging.basicConfig(
            level=runtime_settings.log_level.upper(),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        application.state.model = None
        application.state.model_error = None
        try:
            application.state.model = model_loader(runtime_settings)
        except ModelLoadError as exc:
            application.state.model_error = exc
            LOGGER.error("Application started without a ready champion model")
        yield
        LOGGER.info("Model-serving application stopped")

    application = FastAPI(
        title="Airbnb Price Predictor",
        version="1.0.0",
        description="Serve one NYC listing using an MLflow Registry alias.",
        lifespan=lifespan,
    )

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Return a cheap liveness result without invoking dependencies."""
        return HealthResponse()

    @application.get("/ready", response_model=ReadinessResponse)
    async def ready(request: Request) -> ReadinessResponse:
        """Return readiness only after startup loaded the registry model."""
        if getattr(request.app.state, "model", None) is None:
            raise HTTPException(status_code=503, detail=SAFE_LOAD_ERROR)
        return ReadinessResponse(
            model=runtime_settings.model_name,
            alias=runtime_settings.model_alias,
        )

    @application.post("/predict", response_model=PredictionResponse)
    async def predict(request: Request, listing: ListingFeatures) -> PredictionResponse:
        """Validate one listing and return a sanitized model prediction."""
        model: PredictionModel | None = getattr(request.app.state, "model", None)
        if model is None:
            raise HTTPException(status_code=503, detail=SAFE_LOAD_ERROR)
        try:
            values = np.asarray(model.predict(listing.to_model_frame())).reshape(-1)
            if len(values) != 1:
                raise ValueError("model did not return exactly one value")
            predicted_price = float(values[0])
            if not np.isfinite(predicted_price) or predicted_price < 0.0:
                raise ValueError("model returned an invalid price")
        except Exception:
            LOGGER.exception("Champion prediction failed")
            raise HTTPException(status_code=500, detail=SAFE_PREDICTION_ERROR) from None
        LOGGER.info("Completed prediction with model alias %s", runtime_settings.model_alias)
        return PredictionResponse(
            predicted_price=predicted_price,
            model_name=runtime_settings.model_name,
            model_alias=runtime_settings.model_alias,
        )

    return application


app = create_app()
