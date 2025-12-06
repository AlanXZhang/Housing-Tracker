"""Criteria filtering for apartment listings."""

import logging
from dataclasses import dataclass
from typing import Optional

from apartment_tracker.config import FiltersConfig, PreferredFilters, RequiredFilters
from apartment_tracker.models.schemas import FilterResult, ListingData

logger = logging.getLogger(__name__)


@dataclass
class ScoringWeights:
    """Weights for scoring preferred criteria."""

    facing_south_sw: int = 15  # Highest priority
    sqft_850_plus: int = 5
    bedroom_2b2b: int = 4
    high_floor_per_level: int = 3
    no_building_view: int = 4


class CriteriaFilter:
    """Filter listings based on required and preferred criteria."""

    def __init__(
        self,
        required: Optional[RequiredFilters] = None,
        preferred: Optional[PreferredFilters] = None,
        weights: Optional[ScoringWeights] = None,
    ):
        self.required = required or RequiredFilters()
        self.preferred = preferred or PreferredFilters()
        self.weights = weights or ScoringWeights()

    @classmethod
    def from_config(cls, config: FiltersConfig) -> "CriteriaFilter":
        """Create a CriteriaFilter from config."""
        return cls(
            required=config.required,
            preferred=config.preferred,
        )

    def filter(self, listing: ListingData) -> FilterResult:
        """Apply filters to a listing and return results.

        Args:
            listing: The listing to filter.

        Returns:
            FilterResult with pass/fail status, score, and reasons.
        """
        reasons: list[str] = []
        score = 0

        # Check required criteria
        passes_required = self._check_required(listing, reasons)

        # Check preferred direction (special flag for notification logic)
        passes_preferred_direction = self._check_preferred_direction(listing)

        # Calculate score for preferred criteria
        if passes_required:
            score = self._calculate_score(listing, reasons)

        return FilterResult(
            listing=listing,
            passes_required=passes_required,
            passes_preferred_direction=passes_preferred_direction,
            score=score,
            reasons=reasons,
        )

    def _check_required(self, listing: ListingData, reasons: list[str]) -> bool:
        """Check if listing passes all required criteria."""
        passes = True

        # Floor check (must be >= min_floor, which defaults to 2)
        if listing.floor is not None:
            if listing.floor < self.required.min_floor:
                reasons.append(f"❌ Floor {listing.floor} < {self.required.min_floor}")
                passes = False
            else:
                reasons.append(f"✅ Floor {listing.floor}")
        else:
            reasons.append("⚠️ Floor unknown")

        # Square footage check
        if listing.sqft < self.required.min_sqft:
            reasons.append(f"❌ {listing.sqft} sqft < {self.required.min_sqft}")
            passes = False
        else:
            reasons.append(f"✅ {listing.sqft} sqft")

        # Bedrooms check
        if listing.bedrooms < self.required.min_bedrooms:
            reasons.append(f"❌ {listing.bedrooms}BR < {self.required.min_bedrooms}BR")
            passes = False
        else:
            reasons.append(f"✅ {listing.bedrooms}BR")

        # Bathrooms check
        if listing.bathrooms < self.required.min_bathrooms:
            reasons.append(f"❌ {listing.bathrooms}BA < {self.required.min_bathrooms}BA")
            passes = False
        else:
            reasons.append(f"✅ {listing.bathrooms}BA")

        # Price check
        if listing.price > self.required.max_price:
            reasons.append(f"❌ ${listing.price:,.0f} > ${self.required.max_price:,}")
            passes = False
        else:
            reasons.append(f"✅ ${listing.price:,.0f}")

        return passes

    def _check_preferred_direction(self, listing: ListingData) -> bool:
        """Check if listing has preferred south/southwest direction."""
        if not listing.facing_direction:
            return False

        direction = listing.facing_direction.upper()
        preferred = [d.upper() for d in self.preferred.preferred_directions]
        return direction in preferred

    def _calculate_score(self, listing: ListingData, reasons: list[str]) -> int:
        """Calculate score based on preferred criteria."""
        score = 0

        # South/Southwest facing (highest priority)
        if self._check_preferred_direction(listing):
            score += self.weights.facing_south_sw
            reasons.append(f"⭐ {listing.facing_direction} facing (+{self.weights.facing_south_sw})")

        # 850+ sqft preferred
        if listing.sqft >= self.preferred.min_sqft_preferred:
            score += self.weights.sqft_850_plus
            reasons.append(f"⭐ {listing.sqft} sqft (+{self.weights.sqft_850_plus})")

        # 2BR/2BA preferred
        if (listing.bedrooms >= self.preferred.preferred_bedrooms and
            listing.bathrooms >= self.preferred.preferred_bathrooms):
            score += self.weights.bedroom_2b2b
            reasons.append(f"⭐ {listing.bedrooms}BR/{listing.bathrooms}BA (+{self.weights.bedroom_2b2b})")

        # Higher floors preferred (bonus per floor above 2nd)
        if listing.floor and listing.floor > 2:
            floor_bonus = (listing.floor - 2) * self.weights.high_floor_per_level
            score += floor_bonus
            reasons.append(f"⭐ Floor {listing.floor} (+{floor_bonus})")

        # Not facing a building
        if listing.view_type and listing.view_type.lower() != "building":
            score += self.weights.no_building_view
            reasons.append(f"⭐ {listing.view_type} view (+{self.weights.no_building_view})")

        return score

    def filter_batch(self, listings: list[ListingData]) -> list[FilterResult]:
        """Filter multiple listings.

        Args:
            listings: List of listings to filter.

        Returns:
            List of FilterResults, sorted by score (highest first).
        """
        results = [self.filter(listing) for listing in listings]
        # Sort by: passes_required first, then by score (descending)
        results.sort(key=lambda r: (r.passes_required, r.score), reverse=True)
        return results

    def get_notifiable(self, listings: list[ListingData]) -> list[FilterResult]:
        """Get listings that should trigger notifications.

        According to requirements: Alert if passes required AND faces S/SW.

        Args:
            listings: List of listings to filter.

        Returns:
            List of FilterResults that should trigger notifications.
        """
        results = self.filter_batch(listings)
        return [r for r in results if r.should_notify]
