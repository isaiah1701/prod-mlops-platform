"""Focused tests for safe champion registration helpers."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, cast

import pytest
from mlflow.entities import Run

from scripts.register_model import find_logged_model, get_required_run_id

LOGGER = logging.getLogger(__name__)


def test_champion_run_id_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject registration when no explicit champion run was selected."""
    monkeypatch.delenv("CHAMPION_RUN_ID", raising=False)
    with pytest.raises(ValueError, match="CHAMPION_RUN_ID is required"):
        get_required_run_id()


def test_champion_run_id_must_be_mlflow_hex(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject malformed run identifiers before contacting MLflow."""
    monkeypatch.setenv("CHAMPION_RUN_ID", "not-a-run")
    with pytest.raises(ValueError, match="32-character hexadecimal"):
        get_required_run_id()


def test_find_logged_model_resolves_actual_mlflow3_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Select the newest ready logged model named by the training code."""
    older = SimpleNamespace(
        name="model",
        status=SimpleNamespace(value="READY"),
        creation_timestamp=10,
        model_id="old",
    )
    newer = SimpleNamespace(
        name="model",
        status=SimpleNamespace(value="READY"),
        creation_timestamp=20,
        model_id="new",
    )

    def fake_search_logged_models(**kwargs: object) -> list[Any]:
        """Return two matching logged models without contacting MLflow."""
        del kwargs
        return [older, newer]

    monkeypatch.setattr(
        "scripts.register_model.mlflow.search_logged_models",
        fake_search_logged_models,
    )
    run = cast(
        Run,
        cast(
            Any,
            SimpleNamespace(info=SimpleNamespace(experiment_id="1", run_id="a" * 32)),
        ),
    )
    assert find_logged_model(run).model_id == "new"
