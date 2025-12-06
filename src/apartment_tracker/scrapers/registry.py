"""Scraper registry for managing multiple scraper types."""

from typing import Type

from apartment_tracker.scrapers.base import BaseScraper
from apartment_tracker.scrapers.irvine import IrvineCompanyScraper


# Registry mapping management company names to scraper classes
SCRAPER_REGISTRY: dict[str, Type[BaseScraper]] = {
    "irvine": IrvineCompanyScraper,
    "irvine_company": IrvineCompanyScraper,
    # Future scrapers:
    # "prometheus": PrometheusScraper,
    # "essex": EssexScraper,
    # "greystar": GreystarScraper,
}


def get_scraper(management_company: str) -> Type[BaseScraper]:
    """Get the appropriate scraper class for a management company.

    Args:
        management_company: Name of the management company (e.g., 'irvine', 'prometheus')

    Returns:
        The scraper class for that management company.

    Raises:
        ValueError: If no scraper exists for the given management company.
    """
    key = management_company.lower().strip()
    if key not in SCRAPER_REGISTRY:
        available = ", ".join(SCRAPER_REGISTRY.keys())
        raise ValueError(
            f"No scraper found for '{management_company}'. Available: {available}"
        )
    return SCRAPER_REGISTRY[key]


def register_scraper(name: str, scraper_class: Type[BaseScraper]) -> None:
    """Register a new scraper class.

    Args:
        name: The management company name to register.
        scraper_class: The scraper class to register.
    """
    SCRAPER_REGISTRY[name.lower().strip()] = scraper_class


def list_scrapers() -> list[str]:
    """List all registered scraper names."""
    return list(SCRAPER_REGISTRY.keys())
