"""Tests for the filtering criteria logic."""

import pytest
from decimal import Decimal

from apartment_tracker.models.schemas import ListingData


class TestListingData:
    """Tests for ListingData schema."""

    def test_id_generation(self):
        """Test that ID is generated deterministically from address and unit."""
        listing1 = ListingData(
            community_name="Test Community",
            address="123 Main St, Santa Clara, CA",
            unit_number="Unit 305",
            price=Decimal("3500"),
            bedrooms=1,
            bathrooms=1,
            sqft=750,
            listing_url="https://example.com",
        )

        listing2 = ListingData(
            community_name="Test Community",
            address="123 Main St, Santa Clara, CA",
            unit_number="Unit 305",
            price=Decimal("3600"),  # Different price
            bedrooms=1,
            bathrooms=1,
            sqft=750,
            listing_url="https://example.com",
        )

        # Same address + unit = same ID
        assert listing1.id == listing2.id

    def test_id_different_units(self):
        """Test that different units have different IDs."""
        listing1 = ListingData(
            community_name="Test Community",
            address="123 Main St",
            unit_number="Unit 305",
            price=Decimal("3500"),
            bedrooms=1,
            bathrooms=1,
            sqft=750,
            listing_url="https://example.com",
        )

        listing2 = ListingData(
            community_name="Test Community",
            address="123 Main St",
            unit_number="Unit 306",  # Different unit
            price=Decimal("3500"),
            bedrooms=1,
            bathrooms=1,
            sqft=750,
            listing_url="https://example.com",
        )

        assert listing1.id != listing2.id

    def test_id_case_insensitive(self):
        """Test that ID generation is case-insensitive."""
        listing1 = ListingData(
            community_name="Test",
            address="123 MAIN ST",
            unit_number="UNIT 305",
            price=Decimal("3500"),
            bedrooms=1,
            bathrooms=1,
            sqft=750,
            listing_url="https://example.com",
        )

        listing2 = ListingData(
            community_name="Test",
            address="123 main st",
            unit_number="unit 305",
            price=Decimal("3500"),
            bedrooms=1,
            bathrooms=1,
            sqft=750,
            listing_url="https://example.com",
        )

        assert listing1.id == listing2.id
