"""Database models using SQLAlchemy."""

import hashlib
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class Community(Base):
    """Apartment community (complex) model."""

    __tablename__ = "communities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    management_company: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(String(500))
    website_url: Mapped[str] = mapped_column(String(500), nullable=False)
    community_map_path: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    listings: Mapped[list["Listing"]] = relationship("Listing", back_populates="community")


class Listing(Base):
    """Individual apartment listing model."""

    __tablename__ = "listings"

    # Hash of address:unit_number (first 16 chars of SHA256)
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    community_id: Mapped[int] = mapped_column(ForeignKey("communities.id"), nullable=False)

    # Basic info
    unit_number: Mapped[str] = mapped_column(String(50), nullable=False)
    floor: Mapped[Optional[int]] = mapped_column(Integer)
    floor_plan_name: Mapped[Optional[str]] = mapped_column(String(100))
    floor_plan_image_path: Mapped[Optional[str]] = mapped_column(String(500))

    # Specs
    bedrooms: Mapped[int] = mapped_column(Integer, nullable=False)
    bathrooms: Mapped[int] = mapped_column(Integer, nullable=False)
    sqft: Mapped[int] = mapped_column(Integer, nullable=False)

    # LLM-inferred fields
    facing_direction: Mapped[Optional[str]] = mapped_column(String(10))  # N, NE, E, SE, S, SW, W, NW
    view_type: Mapped[Optional[str]] = mapped_column(String(50))  # courtyard, street, building, unknown
    direction_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # URLs and timestamps
    listing_url: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    community: Mapped["Community"] = relationship("Community", back_populates="listings")
    price_history: Mapped[list["PriceHistory"]] = relationship(
        "PriceHistory", back_populates="listing"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="listing"
    )

    @staticmethod
    def generate_id(address: str, unit_number: str) -> str:
        """Generate a deterministic ID from address and unit number.

        Uses first 16 characters of SHA256 hash to ensure uniqueness
        while keeping IDs manageable.
        """
        key = f"{address.lower().strip()}:{unit_number.lower().strip()}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class PriceHistory(Base):
    """Price history for a listing over time."""

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), nullable=False)

    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    available_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    listing: Mapped["Listing"] = relationship("Listing", back_populates="price_history")


class DirectionCache(Base):
    """Cache for LLM-inferred directions to avoid redundant API calls."""

    __tablename__ = "direction_cache"

    # Key is "address:unit_number" hash
    unit_key: Mapped[str] = mapped_column(String(16), primary_key=True)

    facing_direction: Mapped[Optional[str]] = mapped_column(String(10))
    view_type: Mapped[Optional[str]] = mapped_column(String(50))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    cached_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class Notification(Base):
    """Record of sent notifications."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), nullable=False)

    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)  # discord, email, sms
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # sent, failed, pending

    # Relationships
    listing: Mapped["Listing"] = relationship("Listing", back_populates="notifications")


def get_engine(database_url: str):
    """Create a database engine."""
    return create_engine(database_url, echo=False)


def create_tables(engine) -> None:
    """Create all database tables."""
    Base.metadata.create_all(engine)


def get_session(engine) -> Session:
    """Create a new database session."""
    return Session(engine)
