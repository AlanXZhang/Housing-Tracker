"""Pydantic schemas for data validation and serialization."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class ListingData(BaseModel):
    """Scraped listing data from a website."""

    # Required fields
    community_name: str
    address: str
    unit_number: str
    price: int  # Monthly rent in dollars (rounded up if needed)
    bedrooms: float  # 0 = studio, 0.5 = loft/studio, 1.5 = 1bed+den, 2.5 = loft/2bed
    bathrooms: float  # 0.5 = half bath, 1.5 = 1 full + 1 half
    sqft: int  # Minimum from range (e.g., 1,067-1,123 → 1067)
    listing_url: str

    # Optional fields
    floor: Optional[int] = None
    floor_plan_name: Optional[str] = None
    floor_plan_image_url: Optional[str] = None
    available_date: Optional[datetime] = None  # Full date with year
    lease_term_months: Optional[int] = None  # e.g., 13, 14
    features: list[str] = Field(default_factory=list)  # e.g., ["2nd Floor", "Courtyard view"]

    # LLM-inferred fields (populated later)
    facing_direction: Optional[str] = None
    view_type: Optional[str] = None

    @computed_field
    @property
    def id(self) -> str:
        """Generate deterministic ID from address and unit number."""
        import hashlib

        key = f"{self.address.lower().strip()}:{self.unit_number.lower().strip()}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class CommunityData(BaseModel):
    """Community data from configuration or scraping."""

    name: str
    management_company: str
    website_url: str
    address: Optional[str] = None


class PriceHistoryEntry(BaseModel):
    """A single price history entry."""

    price: Decimal
    available_date: Optional[datetime] = None
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class DirectionResult(BaseModel):
    """Result from LLM direction detection."""

    facing_direction: Optional[str] = None  # N, NE, E, SE, S, SW, W, NW
    view_type: Optional[str] = None  # courtyard, street, building, unknown
    confidence: float = 0.0  # 0.0 to 1.0


class FilterResult(BaseModel):
    """Result of filtering a listing."""

    listing: ListingData
    passes_required: bool
    passes_preferred_direction: bool
    score: int = 0
    reasons: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def should_notify(self) -> bool:
        """Determine if this listing should trigger a notification."""
        return self.passes_required and self.passes_preferred_direction


class NotificationPayload(BaseModel):
    """Payload for sending a notification."""

    listing: ListingData
    filter_result: FilterResult
    is_new: bool = True
    price_changed: bool = False
    previous_price: Optional[Decimal] = None
