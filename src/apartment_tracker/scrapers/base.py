"""Base scraper class for apartment websites."""

import asyncio
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, Page, Playwright, async_playwright

from apartment_tracker.models.schemas import ListingData


class BaseScraper(ABC):
    """Abstract base class for apartment website scrapers.

    All scrapers should inherit from this class and implement the
    abstract methods for their specific website.
    """

    # Subclasses should override these
    MANAGEMENT_COMPANY: str = "unknown"
    BASE_URL: str = ""

    def __init__(
        self,
        headless: bool = True,
        request_delay_seconds: int = 45,
        screenshot_on_error: bool = True,
        screenshot_dir: Optional[Path] = None,
    ):
        self.headless = headless
        self.request_delay_seconds = request_delay_seconds
        self.screenshot_on_error = screenshot_on_error
        self.screenshot_dir = screenshot_dir or Path("data/screenshots")
        self.logger = logging.getLogger(self.__class__.__name__)

        # Playwright objects (initialized in __aenter__)
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    async def __aenter__(self):
        """Context manager entry - launch browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
        )
        self.logger.info(f"Browser launched (headless={self.headless})")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self.logger.info("Browser closed")

    async def new_page(self) -> Page:
        """Create a new browser page with default settings."""
        if not self._browser:
            raise RuntimeError("Browser not initialized. Use async with.")

        context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        return page

    async def delay(self) -> None:
        """Wait between requests to avoid rate limiting."""
        self.logger.debug(f"Waiting {self.request_delay_seconds}s before next request")
        await asyncio.sleep(self.request_delay_seconds)

    async def save_screenshot(self, page: Page, name: str) -> Path:
        """Save a screenshot of the current page."""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{name}.png"
        await page.screenshot(path=str(path), full_page=True)
        self.logger.info(f"Screenshot saved: {path}")
        return path

    async def safe_navigate(self, page: Page, url: str, wait_until: str = "networkidle") -> bool:
        """Navigate to a URL with error handling and optional screenshot on failure.

        Returns:
            True if navigation succeeded, False otherwise.
        """
        try:
            self.logger.info(f"Navigating to: {url}")
            await page.goto(url, wait_until=wait_until, timeout=60000)
            return True
        except Exception as e:
            self.logger.error(f"Navigation failed: {e}")
            if self.screenshot_on_error:
                await self.save_screenshot(page, f"error_{self.__class__.__name__}")
            return False

    @abstractmethod
    async def scrape_availability(self, url: str) -> list[ListingData]:
        """Scrape availability listings from the given URL.

        This is the main method that subclasses must implement.

        Args:
            url: The availability page URL to scrape.

        Returns:
            A list of ListingData objects representing available units.
        """
        pass

    @abstractmethod
    async def get_community_name(self, page: Page) -> str:
        """Extract the community name from the page.

        Args:
            page: The Playwright page object.

        Returns:
            The name of the apartment community.
        """
        pass

    @abstractmethod
    async def get_community_address(self, page: Page) -> str:
        """Extract the community address from the page.

        Args:
            page: The Playwright page object.

        Returns:
            The address of the apartment community.
        """
        pass

    async def download_image(self, url: str, save_path: Path) -> bool:
        """Download an image from a URL.

        Args:
            url: The image URL.
            save_path: Where to save the image.

        Returns:
            True if download succeeded, False otherwise.
        """
        try:
            import httpx

            save_path.parent.mkdir(parents=True, exist_ok=True)
            async with httpx.AsyncClient() as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                save_path.write_bytes(response.content)
            self.logger.info(f"Image downloaded: {save_path}")
            return True
        except Exception as e:
            self.logger.error(f"Image download failed: {e}")
            return False
