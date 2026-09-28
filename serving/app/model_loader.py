"""Load prediction models exclusively from an MLflow Registry alias."""

from __future__ import annotations

import logging
from typing import Protocol

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd

from serving.app.config import Settings

LOGGER = logging.getLogger(__name__)


class PredictionModel(Protocol):
    """Describe the DataFrame prediction interface required by the API."""

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """Predict one nightly price for every input row."""
        ...


class ModelLoadError(RuntimeError):
    """Indicate that an aliased registry model could not be loaded."""


def build_model_uri(settings: Settings) -> str:
    """Build the registry URI without coupling inference to a run ID."""
    return f"models:/{settings.model_name}@{settings.model_alias}"


def load_champion_model(settings: Settings) -> PredictionModel:
    """Load the configured registry model with its persisted preprocessing."""
    model_uri = build_model_uri(settings)
    LOGGER.info("Loading model from registry URI %s", model_uri)
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    try:
        model = mlflow.sklearn.load_model(model_uri)
    except Exception as exc:
        LOGGER.error("Registry model could not be loaded from %s", model_uri)
        raise ModelLoadError("Configured registry model is unavailable") from exc
    LOGGER.info("Registry model loaded successfully from %s", model_uri)
    return model
