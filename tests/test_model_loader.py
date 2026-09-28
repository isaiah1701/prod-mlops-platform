"""Unit tests for registry-only model loading and configuration."""

from __future__ import annotations

import logging

import pytest

from serving.app.config import Settings
from serving.app.model_loader import build_model_uri, load_champion_model

LOGGER = logging.getLogger(__name__)


def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use documented local defaults when environment variables are absent."""
    for name in ("MLFLOW_TRACKING_URI", "MODEL_NAME", "MODEL_ALIAS", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    assert settings.mlflow_tracking_uri == "http://localhost:5000"
    assert settings.model_name == "airbnb-price-predictor"
    assert settings.model_alias == "champion"
    assert settings.log_level == "INFO"


def test_model_uri_uses_configured_registry_alias() -> None:
    """Construct an alias URI without an experiment run identifier."""
    settings = Settings(MODEL_NAME="custom-model", MODEL_ALIAS="candidate")
    assert build_model_uri(settings) == "models:/custom-model@candidate"


def test_champion_loader_uses_registry_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set tracking configuration and load through the Registry alias."""
    captured: dict[str, str] = {}
    sentinel = object()

    def fake_set_tracking_uri(uri: str) -> None:
        """Capture the configured tracking URI."""
        captured["tracking_uri"] = uri

    def fake_load_model(uri: str) -> object:
        """Capture the registry URI passed to MLflow."""
        captured["model_uri"] = uri
        return sentinel

    monkeypatch.setattr(
        "serving.app.model_loader.mlflow.set_tracking_uri", fake_set_tracking_uri
    )
    monkeypatch.setattr(
        "serving.app.model_loader.mlflow.sklearn.load_model", fake_load_model
    )
    settings = Settings(
        MLFLOW_TRACKING_URI="http://mlflow.test:5000",
        MODEL_NAME="custom-model",
        MODEL_ALIAS="champion",
    )
    assert load_champion_model(settings) is sentinel
    assert captured == {
        "tracking_uri": "http://mlflow.test:5000",
        "model_uri": "models:/custom-model@champion",
    }
