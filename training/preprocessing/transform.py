"""Build the point-in-time feature dataset consumed by Feast."""

import logging

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)

# AB_NYC_2019 is a static snapshot, not a historical feature table. Every row
# therefore receives the same timezone-aware timestamp. This supports Feast's
# schema, but it must not be interpreted as the time at which a feature changed.
DATASET_SNAPSHOT_TIMESTAMP: pd.Timestamp = pd.Timestamp("2019-07-08T00:00:00Z")
MIDTOWN_LATITUDE = 40.7580
MIDTOWN_LONGITUDE = -73.9855
EARTH_RADIUS_KM = 6371.0088

INPUT_COLUMNS: tuple[str, ...] = (
    "id",
    "neighbourhood_group",
    "neighbourhood",
    "latitude",
    "longitude",
    "room_type",
    "price",
    "minimum_nights",
    "number_of_reviews",
    "last_review",
    "reviews_per_month",
    "calculated_host_listings_count",
    "availability_365",
)

OUTPUT_COLUMNS: tuple[str, ...] = (
    "id",
    "event_timestamp",
    "neighbourhood_group",
    "neighbourhood",
    "latitude",
    "longitude",
    "room_type",
    "minimum_nights",
    "number_of_reviews",
    "reviews_per_month",
    "calculated_host_listings_count",
    "availability_365",
    "has_reviews",
    "availability_ratio",
    "days_since_last_review",
    "minimum_nights_band",
    "availability_band",
    "location_cell",
    "distance_to_midtown_km",
    "neighbourhood_room_type",
    "price_per_night",
)


def calculate_distance_to_midtown_km(
    latitude: pd.Series,
    longitude: pd.Series,
) -> pd.Series:
    """Calculate vectorized Haversine distance from Midtown Manhattan."""
    latitude_radians = np.radians(pd.to_numeric(latitude, errors="coerce"))
    longitude_radians = np.radians(pd.to_numeric(longitude, errors="coerce"))
    midtown_latitude_radians = np.radians(MIDTOWN_LATITUDE)
    midtown_longitude_radians = np.radians(MIDTOWN_LONGITUDE)
    latitude_delta = latitude_radians - midtown_latitude_radians
    longitude_delta = longitude_radians - midtown_longitude_radians
    haversine = (
        np.sin(latitude_delta / 2.0) ** 2
        + np.cos(midtown_latitude_radians)
        * np.cos(latitude_radians)
        * np.sin(longitude_delta / 2.0) ** 2
    )
    return pd.Series(
        2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(haversine)),
        index=latitude.index,
        dtype="float64",
    )


def transform_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return validated, unencoded listing features and the nightly-price target.

    Missing or invalid ``last_review`` values produce
    ``days_since_last_review == -1``. This explicit sentinel distinguishes a
    listing with no known review from one reviewed on the snapshot date.

    Args:
        df: An already-cleaned NYC Airbnb 2019 DataFrame.

    Raises:
        TypeError: If ``df`` is not a pandas DataFrame.
        ValueError: If required columns or valid feature values are missing.
    """
    if not isinstance(df, pd.DataFrame):
        LOGGER.error("Feature transformation requires a pandas DataFrame")
        raise TypeError("df must be a pandas DataFrame")

    LOGGER.info("Transforming %d rows into the Feast feature schema", len(df))

    if df.columns.has_duplicates:
        LOGGER.error("Feature transformation rejected duplicate input columns")
        raise ValueError("Input DataFrame contains duplicate column names")

    missing_columns = sorted(set(INPUT_COLUMNS).difference(df.columns))
    if missing_columns:
        LOGGER.error("Feature transformation is missing columns: %s", missing_columns)
        raise ValueError(f"Missing required input columns: {missing_columns}")

    transformed = df.loc[:, list(INPUT_COLUMNS)].copy()
    transformed["price_per_night"] = pd.to_numeric(
        transformed.pop("price"), errors="coerce"
    )
    transformed["has_reviews"] = (
        pd.to_numeric(transformed["number_of_reviews"], errors="coerce") > 0
    ).astype("int8")
    transformed["availability_ratio"] = (
        pd.to_numeric(transformed["availability_365"], errors="coerce") / 365.0
    )

    last_review = pd.to_datetime(
        transformed.pop("last_review"), errors="coerce", utc=True
    )
    days_since_last_review = (DATASET_SNAPSHOT_TIMESTAMP - last_review).dt.days
    # A missing review is unknown rather than zero days old. Negative values
    # identify the sentinel clearly and avoid imputing false recency.
    transformed["days_since_last_review"] = days_since_last_review.fillna(-1).astype(
        "int64"
    )
    transformed["event_timestamp"] = DATASET_SNAPSHOT_TIMESTAMP
    transformed["minimum_nights_band"] = pd.cut(
        transformed["minimum_nights"],
        bins=[0, 3, 14, 30, np.inf],
        labels=["short", "medium", "long", "extended"],
    ).astype("string")
    transformed["availability_band"] = pd.cut(
        transformed["availability_365"],
        bins=[-1, 0, 90, 180, 300, 365],
        labels=["unavailable", "low", "medium", "high", "very_high"],
    ).astype("string")
    transformed["location_cell"] = (
        transformed["latitude"].round(2).map(lambda value: f"{value:.2f}")
        + "_"
        + transformed["longitude"].round(2).map(lambda value: f"{value:.2f}")
    )
    transformed["distance_to_midtown_km"] = calculate_distance_to_midtown_km(
        transformed["latitude"],
        transformed["longitude"],
    )
    transformed["neighbourhood_room_type"] = (
        transformed["neighbourhood"].astype("string")
        + "__"
        + transformed["room_type"].astype("string")
    )

    result = transformed.loc[:, list(OUTPUT_COLUMNS)]

    if result["id"].isna().any():
        LOGGER.error("Feature transformation found null listing ids")
        raise ValueError("id must not contain null values")
    if result["event_timestamp"].isna().any():
        LOGGER.error("Feature transformation found null event timestamps")
        raise ValueError("event_timestamp must not contain null values")
    if result["price_per_night"].isna().any() or (result["price_per_night"] <= 0).any():
        LOGGER.error("Feature transformation found invalid nightly prices")
        raise ValueError("price_per_night must contain valid positive values")
    if not result["availability_ratio"].between(0.0, 1.0).all():
        LOGGER.error("Feature transformation found availability outside 0..365")
        raise ValueError("availability_ratio must be between 0 and 1")
    engineered_columns = [
        "minimum_nights_band",
        "availability_band",
        "location_cell",
        "distance_to_midtown_km",
        "neighbourhood_room_type",
    ]
    if result[engineered_columns].isna().any().any():
        LOGGER.error("Feature transformation produced null engineered features")
        raise ValueError("Engineered model features must not contain null values")
    if "price" in result.columns:
        LOGGER.error("Feature transformation retained the source price column")
        raise ValueError("price must not be present in the feature dataset")
    if result.columns.has_duplicates:
        LOGGER.error("Feature transformation produced duplicate output columns")
        raise ValueError("Output DataFrame contains duplicate column names")
    if tuple(result.columns) != OUTPUT_COLUMNS:
        LOGGER.error("Feature transformation produced an unexpected schema")
        raise ValueError("Output DataFrame does not match the expected schema")

    LOGGER.info("Feature transformation completed with %d rows", len(result))
    return result
