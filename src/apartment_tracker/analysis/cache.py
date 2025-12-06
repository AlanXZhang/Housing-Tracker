"""Direction caching to avoid redundant LLM API calls."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from apartment_tracker.models.database import DirectionCache
from apartment_tracker.models.schemas import DirectionResult

logger = logging.getLogger(__name__)


class DirectionCacheManager:
    """Manages caching of LLM direction detection results."""

    def __init__(self, session: Session):
        self.session = session

    def get_cached(self, unit_key: str) -> Optional[DirectionResult]:
        """Get cached direction result for a unit.

        Args:
            unit_key: The unique key for the unit (typically listing ID).

        Returns:
            DirectionResult if cached, None otherwise.
        """
        try:
            cached = self.session.get(DirectionCache, unit_key)
            if cached:
                logger.debug(f"Cache hit for {unit_key}")
                return DirectionResult(
                    facing_direction=cached.facing_direction,
                    view_type=cached.view_type,
                    confidence=cached.confidence or 0.0,
                )
        except Exception as e:
            logger.warning(f"Error reading cache: {e}")

        return None

    def set_cached(self, unit_key: str, result: DirectionResult) -> None:
        """Cache a direction result for a unit.

        Args:
            unit_key: The unique key for the unit.
            result: The DirectionResult to cache.
        """
        try:
            existing = self.session.get(DirectionCache, unit_key)

            if existing:
                # Update existing cache entry
                existing.facing_direction = result.facing_direction
                existing.view_type = result.view_type
                existing.confidence = result.confidence
                existing.cached_at = datetime.utcnow()
            else:
                # Create new cache entry
                cache_entry = DirectionCache(
                    unit_key=unit_key,
                    facing_direction=result.facing_direction,
                    view_type=result.view_type,
                    confidence=result.confidence,
                    cached_at=datetime.utcnow(),
                )
                self.session.add(cache_entry)

            self.session.commit()
            logger.debug(f"Cached direction for {unit_key}: {result.facing_direction}")

        except Exception as e:
            logger.warning(f"Error writing cache: {e}")
            self.session.rollback()

    def invalidate(self, unit_key: str) -> bool:
        """Invalidate (delete) a cached entry.

        Args:
            unit_key: The unique key for the unit.

        Returns:
            True if an entry was deleted, False otherwise.
        """
        try:
            existing = self.session.get(DirectionCache, unit_key)
            if existing:
                self.session.delete(existing)
                self.session.commit()
                return True
        except Exception as e:
            logger.warning(f"Error invalidating cache: {e}")
            self.session.rollback()

        return False

    def get_stats(self) -> dict:
        """Get cache statistics.

        Returns:
            Dict with cache stats (total entries, high/low confidence counts).
        """
        try:
            total = self.session.query(DirectionCache).count()
            high_confidence = self.session.query(DirectionCache).filter(
                DirectionCache.confidence >= 0.7
            ).count()
            low_confidence = self.session.query(DirectionCache).filter(
                DirectionCache.confidence < 0.5
            ).count()

            return {
                "total_cached": total,
                "high_confidence": high_confidence,
                "low_confidence": low_confidence,
            }
        except Exception:
            return {"total_cached": 0, "high_confidence": 0, "low_confidence": 0}
