"""Train and log the champion Airbnb nightly-price model."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from collections.abc import Sequence
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from catboost import CatBoostRegressor
from feast import FeatureStore
from feast.errors import FeatureServiceNotFoundException
from feast.feature_service import FeatureService
from mlflow.models import infer_signature
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import train_test_split
from sklearn.utils.validation import check_is_fitted

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEATURE_REPO_PATH = PROJECT_ROOT / "feature_repo"
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "listing_features.parquet"
FEATURE_SERVICE_NAME = "airbnb_price_model_v1"
EXPERIMENT_NAME = "airbnb-price-prediction"
MODEL_NAME = "catboost_log_price_seed_ensemble"
TARGET_COLUMN = "price_per_night"
ENTITY_COLUMNS: tuple[str, str] = ("id", "event_timestamp")
CATEGORICAL_FEATURES: tuple[str, ...] = (
    "neighbourhood_group",
    "neighbourhood",
    "room_type",
    "minimum_nights_band",
    "availability_band",
    "location_cell",
    "neighbourhood_room_type",
)
EXCLUDED_FEATURES: frozenset[str] = frozenset(
    {"availability_ratio", "neighbourhood_room_type"}
)
RANDOM_STATE = 42
TEST_SIZE = 0.2
HASH_CHUNK_SIZE = 1024 * 1024
ENSEMBLE_RANDOM_STATES: tuple[int, ...] = (42, 7, 123)
ENSEMBLE_ITERATIONS: tuple[int, ...] = (1440, 1565, 1589)
LEARNING_RATE = 0.04
TREE_DEPTH = 10
L2_LEAF_REG = 8.0
RANDOM_STRENGTH = 1.0


def load_labels(data_path: Path) -> pd.DataFrame:
    """Load validated entity metadata and nightly-price labels."""
    LOGGER.info("Loading training labels from %s", data_path)
    if not data_path.is_file():
        LOGGER.error("Transformed dataset does not exist: %s", data_path)
        raise FileNotFoundError(f"Transformed Parquet dataset not found: {data_path}")
    required = (*ENTITY_COLUMNS, TARGET_COLUMN)
    missing = sorted(set(required).difference(pq.read_schema(data_path).names))
    if missing:
        LOGGER.error("Training labels are missing columns: %s", missing)
        raise ValueError(f"Transformed dataset is missing columns: {missing}")
    labels = pd.read_parquet(data_path, columns=list(required))
    if labels.empty or labels["id"].isna().any():
        LOGGER.error("Training labels are empty or contain null listing IDs")
        raise ValueError("Training labels require rows and non-null IDs")
    labels["event_timestamp"] = pd.to_datetime(
        labels["event_timestamp"], errors="coerce", utc=True
    )
    if labels["event_timestamp"].isna().any():
        LOGGER.error("Training labels contain invalid timestamps")
        raise ValueError("event_timestamp must contain valid values")
    labels[TARGET_COLUMN] = pd.to_numeric(labels[TARGET_COLUMN], errors="coerce")
    target = labels[TARGET_COLUMN].to_numpy()
    if not np.isfinite(target).all() or (target <= 0).any():
        LOGGER.error("Training labels contain invalid nightly prices")
        raise ValueError(f"{TARGET_COLUMN} must contain finite positive values")
    if labels.duplicated(subset=list(ENTITY_COLUMNS)).any():
        LOGGER.error("Training labels contain duplicate entity timestamp keys")
        raise ValueError("id and event_timestamp must uniquely identify rows")
    LOGGER.info("Loaded %d training label rows", len(labels))
    return labels


def get_feature_names(feature_service: FeatureService) -> tuple[str, ...]:
    """Return validated predictive feature names from a Feast service."""
    names = tuple(
        feature.name
        for projection in feature_service.feature_view_projections
        for feature in projection.features
    )
    if not names or len(names) != len(set(names)):
        LOGGER.error("FeatureService must contain unique predictive features")
        raise ValueError("FeatureService must contain unique predictive features")
    leaked = sorted({*ENTITY_COLUMNS, TARGET_COLUMN}.intersection(names))
    if leaked:
        LOGGER.error("FeatureService contains forbidden inputs: %s", leaked)
        raise ValueError(f"FeatureService contains forbidden model inputs: {leaked}")
    return names


def load_features_from_feast(
    feature_repo_path: Path,
    entity_df: pd.DataFrame,
    feature_service_name: str = FEATURE_SERVICE_NAME,
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Retrieve point-in-time-correct model features from Feast."""
    LOGGER.info("Loading Feast feature store from %s", feature_repo_path)
    store = FeatureStore(repo_path=str(feature_repo_path))
    try:
        service = store.get_feature_service(feature_service_name)
    except FeatureServiceNotFoundException as exc:
        LOGGER.error("FeatureService %s was not found", feature_service_name)
        raise ValueError(
            f"Feast FeatureService {feature_service_name!r} was not found"
        ) from exc
    names = get_feature_names(service)
    LOGGER.info("Retrieving %d historical features", len(names))
    historical = store.get_historical_features(
        entity_df=entity_df.loc[:, list(ENTITY_COLUMNS)], features=service
    ).to_df()
    return historical, names


def build_training_dataset(
    labels: pd.DataFrame,
    historical_features: pd.DataFrame,
    feature_names: Sequence[str],
) -> tuple[pd.DataFrame, pd.Series]:
    """Align Feast features to labels without target or entity leakage."""
    if labels.empty or historical_features.empty:
        LOGGER.error("Cannot build a training dataset with zero rows")
        raise ValueError("Training labels and historical features must contain rows")
    if len(labels) != len(historical_features):
        LOGGER.error("Feature and target row counts do not match")
        raise ValueError("Historical feature and target row counts do not match")
    names = list(feature_names)
    if len(names) != len(set(names)):
        LOGGER.error("Duplicate predictive feature names were supplied")
        raise ValueError("Predictive feature names must be unique")
    missing_labels = sorted(
        {*ENTITY_COLUMNS, TARGET_COLUMN}.difference(labels.columns)
    )
    if missing_labels:
        LOGGER.error("Labels are missing columns: %s", missing_labels)
        raise ValueError(f"Labels are missing required columns: {missing_labels}")
    missing_features = sorted(
        {*ENTITY_COLUMNS, *names}.difference(historical_features.columns)
    )
    if missing_features:
        LOGGER.error("Historical features are missing: %s", missing_features)
        raise ValueError(f"Historical features are missing columns: {missing_features}")
    if TARGET_COLUMN in historical_features.columns or TARGET_COLUMN in names:
        LOGGER.error("Target leakage detected in historical features")
        raise ValueError(f"Unexpected {TARGET_COLUMN} inside model features")
    if set(ENTITY_COLUMNS).intersection(names):
        LOGGER.error("Entity metadata was selected as predictive input")
        raise ValueError("Entity metadata cannot be model features")

    aligned_labels = labels.copy()
    aligned_features = historical_features.copy()
    for frame in (aligned_labels, aligned_features):
        frame["event_timestamp"] = pd.to_datetime(
            frame["event_timestamp"], errors="coerce", utc=True
        )
    if aligned_features[list(ENTITY_COLUMNS)].isna().any().any():
        LOGGER.error("Historical features contain null entity metadata")
        raise ValueError("Historical features contain null entity metadata")
    if aligned_features.duplicated(subset=list(ENTITY_COLUMNS)).any():
        LOGGER.error("Historical features contain duplicate entity keys")
        raise ValueError("Historical features contain duplicate entity timestamp keys")
    label_index = pd.MultiIndex.from_frame(aligned_labels.loc[:, list(ENTITY_COLUMNS)])
    feature_index = pd.MultiIndex.from_frame(
        aligned_features.loc[:, list(ENTITY_COLUMNS)]
    )
    if (
        not label_index.difference(feature_index).empty
        or not feature_index.difference(label_index).empty
    ):
        LOGGER.error("Historical feature keys do not align with labels")
        raise ValueError("Historical feature IDs and timestamps do not align with labels")
    x = (
        aligned_features.set_index(list(ENTITY_COLUMNS))
        .reindex(label_index)
        .loc[:, names]
        .reset_index(drop=True)
    )
    y = aligned_labels[TARGET_COLUMN].reset_index(drop=True).rename(TARGET_COLUMN)
    if x.isna().any().any():
        null_columns = x.columns[x.isna().any()].tolist()
        LOGGER.error("Model features contain null values in %s", null_columns)
        raise ValueError(f"Model features contain null values in: {null_columns}")
    LOGGER.info("Built aligned training dataset with %d rows", len(x))
    return x, y


class CatBoostPriceEnsembleRegressor(RegressorMixin, BaseEstimator):
    """Average robust log-price estimates from three CatBoost models."""

    def __init__(
        self,
        feature_names: tuple[str, ...],
        random_states: tuple[int, ...] = ENSEMBLE_RANDOM_STATES,
        iterations: tuple[int, ...] = ENSEMBLE_ITERATIONS,
        learning_rate: float = LEARNING_RATE,
        depth: int = TREE_DEPTH,
        l2_leaf_reg: float = L2_LEAF_REG,
        random_strength: float = RANDOM_STRENGTH,
    ) -> None:
        """Store the validation-selected champion configuration."""
        self.feature_names = feature_names
        self.random_states = random_states
        self.iterations = iterations
        self.learning_rate = learning_rate
        self.depth = depth
        self.l2_leaf_reg = l2_leaf_reg
        self.random_strength = random_strength

    def _prepare_features(self, x: pd.DataFrame) -> pd.DataFrame:
        """Select model inputs and normalize categorical values."""
        if not isinstance(x, pd.DataFrame):
            LOGGER.error("Champion model requires pandas inputs")
            raise TypeError("x must be a pandas DataFrame")
        selected = [name for name in self.feature_names if name not in EXCLUDED_FEATURES]
        missing = sorted(set(selected).difference(x.columns))
        if missing:
            LOGGER.error("Champion model inputs are missing: %s", missing)
            raise ValueError(f"x is missing model features: {missing}")
        prepared = x.loc[:, selected].copy()
        for name in CATEGORICAL_FEATURES:
            if name in prepared.columns:
                prepared[name] = prepared[name].astype("string").fillna("unknown")
        return prepared

    def fit(
        self, x: pd.DataFrame, y: pd.Series | np.ndarray
    ) -> CatBoostPriceEnsembleRegressor:
        """Fit all champion members on log-transformed positive prices."""
        if not self.random_states or len(self.random_states) != len(self.iterations):
            LOGGER.error("Ensemble seeds and iteration counts do not align")
            raise ValueError(
                "random_states and iterations must be nonempty and have equal length"
            )
        if any(iteration < 1 for iteration in self.iterations):
            LOGGER.error("Ensemble iteration counts must be positive")
            raise ValueError("iterations must contain positive values")
        prepared = self._prepare_features(x)
        target = np.asarray(y, dtype="float64")
        if target.ndim != 1 or len(target) != len(prepared):
            LOGGER.error("Champion feature and target rows do not align")
            raise ValueError("x and y must contain the same number of rows")
        if not np.isfinite(target).all() or (target <= 0).any():
            LOGGER.error("Champion targets must be finite positive prices")
            raise ValueError("y must contain finite positive prices")
        categorical = [
            name for name in CATEGORICAL_FEATURES if name in prepared.columns
        ]
        self.models_: list[CatBoostRegressor] = []
        for random_state, iterations in zip(
            self.random_states, self.iterations, strict=True
        ):
            LOGGER.info(
                "Fitting champion member seed=%d iterations=%d",
                random_state,
                iterations,
            )
            model = CatBoostRegressor(
                loss_function="RMSE",
                iterations=iterations,
                learning_rate=self.learning_rate,
                depth=self.depth,
                l2_leaf_reg=self.l2_leaf_reg,
                random_strength=self.random_strength,
                random_seed=random_state,
                allow_writing_files=False,
                verbose=False,
            )
            model.fit(
                prepared,
                np.log1p(target),
                cat_features=categorical,
                verbose=False,
            )
            self.models_.append(model)
        self.feature_names_in_ = np.asarray(prepared.columns, dtype=object)
        return self

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        """Return the mean member prediction on the dollar scale."""
        check_is_fitted(self, ("models_", "feature_names_in_"))
        prepared = self._prepare_features(x)
        return np.mean(
            [np.expm1(model.predict(prepared)) for model in self.models_], axis=0
        )

    def feature_importances(self) -> dict[str, float]:
        """Return mean feature importance across champion members."""
        check_is_fitted(self, ("models_", "feature_names_in_"))
        values = np.mean([model.feature_importances_ for model in self.models_], axis=0)
        ordered = sorted(
            zip(self.feature_names_in_, values, strict=True),
            key=lambda item: item[1],
            reverse=True,
        )
        return {str(name): float(value) for name, value in ordered}


def evaluate_model(y_true: pd.Series, y_pred: np.ndarray) -> dict[str, float]:
    """Calculate headline regression metrics in dollars."""
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(root_mean_squared_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)),
    }


def evaluate_segments(
    x: pd.DataFrame, y: pd.Series, predictions: np.ndarray
) -> dict[str, float]:
    """Calculate headline and diagnostic segment metrics."""
    metrics = evaluate_model(y, predictions)
    segments = {
        "entire_home": x["room_type"].to_numpy() == "Entire home/apt",
        "private_room": x["room_type"].to_numpy() == "Private room",
        "shared_room": x["room_type"].to_numpy() == "Shared room",
        "at_or_below_250": y.to_numpy() <= 250.0,
        "above_250": y.to_numpy() > 250.0,
        "above_500": y.to_numpy() > 500.0,
        "ordinary_market": y.to_numpy() <= 500.0,
    }
    for name, mask in segments.items():
        positions = np.flatnonzero(mask)
        metrics[f"rows_{name}"] = float(len(positions))
        if len(positions) >= 2:
            scores = evaluate_model(y.iloc[positions], predictions[positions])
            metrics.update(
                {f"{metric}_{name}": value for metric, value in scores.items()}
            )
    metrics["ordinary_market_coverage"] = float(segments["ordinary_market"].mean())
    return metrics


def get_dataset_version(data_path: Path) -> str:
    """Return a deterministic SHA-256 digest of the transformed dataset."""
    if not data_path.is_file():
        LOGGER.error("Cannot version missing dataset: %s", data_path)
        raise FileNotFoundError(f"Transformed Parquet dataset not found: {data_path}")
    digest = hashlib.sha256()
    with data_path.open("rb") as dataset_file:
        while chunk := dataset_file.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def train_and_log_champion(
    model: CatBoostPriceEnsembleRegressor,
    x_train: pd.DataFrame,
    x_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
    *,
    dataset_version: str,
    source_row_count: int,
) -> dict[str, object]:
    """Fit, evaluate, log, and reload-verify the champion model."""
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    metrics = evaluate_segments(x_test, y_test, predictions)
    LOGGER.info("Champion metrics: %s", metrics)
    with mlflow.start_run(run_name="catboost_price_ensemble_champion") as run:
        mlflow.set_tags(
            {
                "champion": "true",
                "promotion_status": "champion",
                "model_family": "catboost_ensemble",
                "artifact_reload_verified": "pending",
            }
        )
        mlflow.log_params(
            {
                "model_name": MODEL_NAME,
                "model_class": type(model).__name__,
                "feature_service_name": FEATURE_SERVICE_NAME,
                "number_of_features": x_train.shape[1],
                "dataset_version": dataset_version,
                "source_row_count": source_row_count,
                "training_row_count": len(x_train),
                "test_row_count": len(x_test),
                "test_size": TEST_SIZE,
                "random_states": model.random_states,
                "member_iterations": model.iterations,
                "learning_rate": model.learning_rate,
                "depth": model.depth,
                "l2_leaf_reg": model.l2_leaf_reg,
                "target_transform": "log1p",
                "aggregation": "mean dollar prediction",
            }
        )
        mlflow.log_metrics(metrics)
        mlflow.log_dict(model.feature_importances(), "feature_importance.json")
        sample = x_train.iloc[:3]
        model_info = mlflow.sklearn.log_model(
            sk_model=model,
            name="model",
            serialization_format="cloudpickle",
            signature=infer_signature(sample, model.predict(sample)),
        )
        loaded = mlflow.sklearn.load_model(model_info.model_uri)
        np.testing.assert_allclose(
            loaded.predict(x_test.iloc[:32]), predictions[:32], rtol=1e-10, atol=1e-10
        )
        mlflow.set_tag("artifact_reload_verified", "true")
        report: dict[str, object] = {
            "run_id": run.info.run_id,
            "model_uri": model_info.model_uri,
            "metrics": metrics,
        }
        mlflow.log_dict(report, "report.json")
        return report


def run_training(
    data_path: Path = DEFAULT_DATA_PATH,
    feature_repo_path: Path = FEATURE_REPO_PATH,
    experiment_name: str = EXPERIMENT_NAME,
) -> dict[str, object]:
    """Run the reproducible Feast-to-MLflow champion pipeline."""
    labels = load_labels(data_path)
    historical, feature_names = load_features_from_feast(
        feature_repo_path, labels.loc[:, list(ENTITY_COLUMNS)]
    )
    x, y = build_training_dataset(labels, historical, feature_names)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    mlflow.set_tracking_uri(
        os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{PROJECT_ROOT / 'mlflow.db'}")
    )
    mlflow.set_experiment(experiment_name)
    return train_and_log_champion(
        CatBoostPriceEnsembleRegressor(tuple(feature_names)),
        x_train,
        x_test,
        y_train,
        y_test,
        dataset_version=get_dataset_version(data_path),
        source_row_count=len(labels),
    )


def _parse_args() -> argparse.Namespace:
    """Parse local training command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path(os.getenv("AIRBNB_FEATURE_DATA_PATH", DEFAULT_DATA_PATH)),
    )
    parser.add_argument("--feature-repo-path", type=Path, default=FEATURE_REPO_PATH)
    parser.add_argument(
        "--experiment-name",
        default=os.getenv("MLFLOW_EXPERIMENT_NAME", EXPERIMENT_NAME),
    )
    return parser.parse_args()


def main() -> None:
    """Configure logging and train the champion model."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    arguments = _parse_args()
    report = run_training(
        data_path=arguments.data_path.expanduser().resolve(),
        feature_repo_path=arguments.feature_repo_path.expanduser().resolve(),
        experiment_name=arguments.experiment_name,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
