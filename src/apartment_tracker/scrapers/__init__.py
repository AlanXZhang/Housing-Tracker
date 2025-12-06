"""Scrapers package."""

from apartment_tracker.scrapers.base import BaseScraper
from apartment_tracker.scrapers.irvine import IrvineCompanyScraper
from apartment_tracker.scrapers.registry import get_scraper, list_scrapers, register_scraper

__all__ = [
    "BaseScraper",
    "IrvineCompanyScraper",
    "get_scraper",
    "list_scrapers",
    "register_scraper",
]
