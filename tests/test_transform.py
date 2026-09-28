"""Unit tests for NYC Airbnb feature transformation."""

import logging

import pandas as pd
import pandas.testing as pdt
import pytest

from training.preprocessing.transform import (
    DATASET_SNAPSHOT_TIMESTAMP,
    OUTPUT_COLUMNS,
    transform_features,
)

LOGGER = logging.getLogger(__name__)


@pytest.fixture
def cleaned_data() -> pd.DataFrame:
    """Return representative cleaned rows, including a listing without a review."""
    LOGGER.debug("Creating the cleaned-data test fixture")
    return pd.DataFrame(
        {
            "id": [101, 102],
            "name": ["Loft", "Flat"],
            "host_id": [1, 2],
            "host_name": ["A", "B"],
            "neighbourhood_group": ["Brooklyn", "Manhattan"],
            "neighbourhood": ["Bushwick", "Harlem"],
            "latitude": [40.69, 40.81],
            "longitude": [-73.92, -73.95],
            "room_type": ["Private room", "Entire home/apt"],
            "price": [75.0, 150.0],
            "minimum_nights": [3, 2],
            "number_of_reviews": [4, 0],
            "last_review": ["2019-07-01", None],
            "reviews_per_month": [1.5, 0.0],
            "calculated_host_listings_count": [1, 2],
            "availability_365": [365, 0],
        }
    )


def test_target_and_leakage_prevention(cleaned_data: pd.DataFrame) -> None:
    """Copy nightly price to the target without retaining leaky price features."""
    LOGGER.debug("Testing target construction and leakage prevention")
    result = transform_features(cleaned_data)

    assert result["price_per_night"].tolist() == [75.0, 150.0]
    assert "price" not in result.columns
    assert "minimum_nights" in result.columns
    assert not any(column.startswith("price_") for column in result.columns[:-1])


def test_engineered_features(cleaned_data: pd.DataFrame) -> None:
    """Calculate review and availability features with defined missing behavior."""
    LOGGER.debug("Testing engineered feature values")
    result = transform_features(cleaned_data)

    assert result["has_reviews"].tolist() == [1, 0]
    assert result["availability_ratio"].tolist() == [1.0, 0.0]
    assert result["days_since_last_review"].tolist() == [7, -1]
    assert result["minimum_nights_band"].tolist() == ["short", "short"]
    assert result["availability_band"].tolist() == ["very_high", "unavailable"]
    assert result["location_cell"].tolist() == ["40.69_-73.92", "40.81_-73.95"]
    assert result["distance_to_midtown_km"].gt(0).all()
    assert result["neighbourhood_room_type"].tolist() == [
        "Bushwick__Private room",
        "Harlem__Entire home/apt",
    ]


def test_event_timestamp_is_fixed_and_timezone_aware(
    cleaned_data: pd.DataFrame,
) -> None:
    """Attach the documented UTC snapshot timestamp to every listing."""
    LOGGER.debug("Testing Feast event timestamps")
    result = transform_features(cleaned_data)

    assert result["event_timestamp"].eq(DATASET_SNAPSHOT_TIMESTAMP).all()
    assert result["event_timestamp"].dt.tz is not None


def test_output_schema(cleaned_data: pd.DataFrame) -> None:
    """Return every expected column once and in deterministic order."""
    LOGGER.debug("Testing the output schema")
    result = transform_features(cleaned_data)

    assert tuple(result.columns) == OUTPUT_COLUMNS
    assert not result.columns.has_duplicates
    assert not {"name", "host_name", "host_id", "price"}.intersection(result.columns)


def test_input_is_not_mutated(cleaned_data: pd.DataFrame) -> None:
    """Leave the caller's DataFrame unchanged."""
    LOGGER.debug("Testing input immutability")
    original = cleaned_data.copy(deep=True)

    transform_features(cleaned_data)

    pdt.assert_frame_equal(cleaned_data, original)


@pytest.mark.parametrize("invalid_price", [0, -1, None, "not-a-price"])
def test_invalid_target_is_rejected(
    cleaned_data: pd.DataFrame, invalid_price: object
) -> None:
    """Reject target values unsuitable for positive-price regression."""
    LOGGER.debug("Testing rejection of invalid target %r", invalid_price)
    cleaned_data["price"] = cleaned_data["price"].astype("object")
    cleaned_data.loc[0, "price"] = invalid_price

    with pytest.raises(ValueError, match="price_per_night"):
        transform_features(cleaned_data)


def test_target_is_not_used_to_derive_features(cleaned_data: pd.DataFrame) -> None:
    """Changing the target alone must not alter any model input feature."""
    LOGGER.debug("Testing that target changes do not leak into model inputs")
    changed_target = cleaned_data.copy()
    changed_target["price"] = [999.0, 888.0]

    baseline = transform_features(cleaned_data).drop(columns="price_per_night")
    changed = transform_features(changed_target).drop(columns="price_per_night")

    pdt.assert_frame_equal(baseline, changed)
