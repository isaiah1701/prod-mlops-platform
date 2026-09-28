"""Schema tests for the Airbnb Feast feature repository."""

import logging
import sys
from pathlib import Path

import pandas as pd

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FEATURE_REPO_PATH = PROJECT_ROOT / "feature_repo"
sys.path.insert(0, str(FEATURE_REPO_PATH))

from entities import listing
from feature_services import airbnb_price_model_v1
from feature_views import LISTING_FEATURE_NAMES, listing_features_view
from sources import FEATURE_DATA_PATH, listing_features_source

REQUIRED_PARQUET_COLUMNS: frozenset[str] = frozenset(
    {
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
    }
)


def test_listing_entity_uses_id_join_key() -> None:
    """Define the listing entity with the expected unique identifier."""
    LOGGER.debug("Testing the listing entity declaration")
    assert listing.name == "listing"
    assert listing.join_key == "id"


def test_listing_feature_view_excludes_identifiers_and_target() -> None:
    """Expose exactly the intended predictive feature fields."""
    LOGGER.debug("Testing the listing feature-view schema")
    feature_names = tuple(field.name for field in listing_features_view.features)

    assert listing_features_view.name == "listing_features"
    assert feature_names == LISTING_FEATURE_NAMES
    assert not {"id", "event_timestamp", "price_per_night"}.intersection(feature_names)


def test_airbnb_feature_service_uses_listing_features() -> None:
    """Expose the listing feature view through the model service."""
    LOGGER.debug("Testing the Airbnb feature-service declaration")
    projections = airbnb_price_model_v1.feature_view_projections

    assert airbnb_price_model_v1.name == "airbnb_price_model_v1"
    assert len(projections) == 1
    assert projections[0].name == "listing_features"
    assert (
        tuple(field.name for field in projections[0].features) == LISTING_FEATURE_NAMES
    )


def test_file_source_uses_absolute_generated_parquet_path() -> None:
    """Resolve the source independently of the process working directory."""
    LOGGER.debug("Testing the listing feature source")
    assert Path(listing_features_source.path).is_absolute()
    assert Path(listing_features_source.path) == FEATURE_DATA_PATH
    assert listing_features_source.timestamp_field == "event_timestamp"
    assert FEATURE_DATA_PATH.is_file()


def test_transformed_parquet_contains_required_schema() -> None:
    """Ensure the persisted dataset satisfies the Feast source contract."""
    LOGGER.debug("Testing the transformed Parquet schema")
    parquet_columns = frozenset(pd.read_parquet(FEATURE_DATA_PATH).columns)

    assert REQUIRED_PARQUET_COLUMNS.issubset(parquet_columns)
