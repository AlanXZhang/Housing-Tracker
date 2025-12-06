"""Direction detection module combining LLM analysis with caching."""

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from apartment_tracker.analysis.cache import DirectionCacheManager
from apartment_tracker.analysis.llm_client import LLMClient
from apartment_tracker.models.schemas import DirectionResult, ListingData

logger = logging.getLogger(__name__)


class DirectionDetector:
    """Detects apartment window direction using LLM with caching."""

    def __init__(
        self,
        session: Session,
        llm_provider: str = "gemini",
        api_key: Optional[str] = None,
    ):
        self.cache = DirectionCacheManager(session)
        self.llm_client = LLMClient(provider=llm_provider, api_key=api_key) if api_key else None

    async def detect(
        self,
        listing: ListingData,
        floor_plan_path: Optional[Path] = None,
        community_map_path: Optional[Path] = None,
        force_refresh: bool = False,
    ) -> DirectionResult:
        """Detect window direction for a listing.

        Uses cache first, falls back to LLM if not cached.

        Args:
            listing: The listing to analyze.
            floor_plan_path: Path to floor plan image.
            community_map_path: Path to community map image.
            force_refresh: If True, skip cache and call LLM.

        Returns:
            DirectionResult with direction, view type, and confidence.
        """
        unit_key = listing.id

        # Check cache first (unless force refresh)
        if not force_refresh:
            cached = self.cache.get_cached(unit_key)
            if cached:
                return cached

        # No LLM client configured - return unknown
        if not self.llm_client:
            logger.warning("LLM client not configured, cannot detect direction")
            return DirectionResult(
                facing_direction=None,
                view_type="unknown",
                confidence=0.0,
            )

        # No images provided - return unknown
        if not floor_plan_path and not community_map_path:
            logger.warning("No images provided for direction detection")
            return DirectionResult(
                facing_direction=None,
                view_type="unknown",
                confidence=0.0,
            )

        # Call LLM for analysis
        logger.info(f"Calling LLM for direction detection: {listing.unit_number}")

        result = await self.llm_client.analyze_direction(
            floor_plan_image_path=floor_plan_path,
            community_map_image_path=community_map_path,
            unit_number=listing.unit_number,
            additional_context=f"Community: {listing.community_name}, Floor: {listing.floor}",
        )

        # Cache the result if we got a meaningful response
        if result.confidence > 0:
            self.cache.set_cached(unit_key, result)

        return result

    async def detect_batch(
        self,
        listings: list[ListingData],
        floor_plan_dir: Optional[Path] = None,
        community_map_path: Optional[Path] = None,
    ) -> dict[str, DirectionResult]:
        """Detect directions for multiple listings.

        Args:
            listings: List of listings to analyze.
            floor_plan_dir: Directory containing floor plan images.
            community_map_path: Path to community map image.

        Returns:
            Dict mapping listing IDs to DirectionResults.
        """
        results = {}

        for listing in listings:
            # Try to find floor plan image for this listing
            floor_plan_path = None
            if floor_plan_dir:
                # Look for floor plan by unit number or floor plan name
                for pattern in [
                    f"*{listing.unit_number}*",
                    f"*{listing.floor_plan_name}*" if listing.floor_plan_name else None,
                ]:
                    if pattern:
                        matches = list(floor_plan_dir.glob(pattern))
                        if matches:
                            floor_plan_path = matches[0]
                            break

            result = await self.detect(
                listing,
                floor_plan_path=floor_plan_path,
                community_map_path=community_map_path,
            )
            results[listing.id] = result

        return results

    def get_cache_stats(self) -> dict:
        """Get direction cache statistics."""
        return self.cache.get_stats()
