"""Irvine Company Apartments scraper."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from playwright.async_api import Page

from apartment_tracker.models.schemas import ListingData
from apartment_tracker.scrapers.base import BaseScraper


class IrvineCompanyScraper(BaseScraper):
    """Scraper for Irvine Company Apartment Homes websites.

    Uses a text-extraction approach since the site has complex dynamic rendering.
    Clicks all expand buttons first, then extracts all visible unit data.
    """

    MANAGEMENT_COMPANY = "irvine"
    BASE_URL = "https://www.irvinecompanyapartments.com"

    async def scrape_availability(self, url: str) -> list[ListingData]:
        """Scrape all available listings from an Irvine Company availability page."""
        page = await self.new_page()
        try:
            if not await self.safe_navigate(page, url):
                return []

            # Wait for the page to fully load
            await page.wait_for_timeout(5000)

            # Get community info
            community_name = await self.get_community_name(page)
            community_address = await self.get_community_address(page)

            self.logger.info(f"Scraping {community_name} at {community_address}")

            # Click all expand buttons to reveal unit data
            await self._expand_all_floor_plans(page)

            # Wait for all content to load
            await page.wait_for_timeout(2000)

            # Extract listings from the full page content
            listings = await self._extract_all_listings(page, community_name, community_address)

            self.logger.info(f"Found {len(listings)} listings at {community_name}")
            return listings

        finally:
            await page.close()

    async def get_community_name(self, page: Page) -> str:
        """Extract the community name from the page."""
        title = await page.title()
        if title:
            parts = title.split('|')
            if len(parts) > 1:
                return parts[-1].strip()
        return "Unknown Community"

    async def get_community_address(self, page: Page) -> str:
        """Extract the community address from the page."""
        try:
            # Try to find address in the page footer or contact section
            address_el = await page.query_selector('.fapt-community-contact__address, address')
            if address_el:
                text = await address_el.inner_text()
                if text:
                    return text.strip().replace('\n', ', ')
        except Exception:
            pass
        return "Santa Clara, CA"

    async def _expand_all_floor_plans(self, page: Page) -> None:
        """Click all expand buttons to reveal unit data."""
        # Find all expand buttons
        expand_buttons = await page.query_selector_all(
            'button[aria-expanded="false"], '
            '.fapt-fp-list-item__acc-trigger-cta'
        )

        self.logger.info(f"Found {len(expand_buttons)} expand buttons to click")

        # Click each button with a small delay
        for i, button in enumerate(expand_buttons):
            try:
                # Check if already expanded
                is_expanded = await button.get_attribute('aria-expanded')
                if is_expanded == 'true':
                    continue

                await button.click()
                await page.wait_for_timeout(500)  # Short delay between clicks

            except Exception as e:
                self.logger.debug(f"Could not click button {i}: {e}")
                continue

        # Give time for all content to load
        await page.wait_for_timeout(2000)

    async def _extract_all_listings(
        self,
        page: Page,
        community_name: str,
        community_address: str,
    ) -> list[ListingData]:
        """Extract all listings from the fully expanded page."""
        listings: list[ListingData] = []

        # Get the full page HTML for parsing
        # We'll look for the pricing table rows
        try:
            # Try to get all pricing table rows
            rows = await page.query_selector_all(
                '.fapt-fp-pricing-table__row:not(:first-child)'
            )

            if rows:
                self.logger.info(f"Found {len(rows)} pricing table rows")
                for row in rows:
                    listing = await self._parse_pricing_row(
                        row, community_name, community_address, page.url
                    )
                    if listing:
                        listings.append(listing)

            # If no structured rows found, fall back to text extraction
            if not listings:
                self.logger.info("No structured rows, trying text extraction")
                listings = await self._extract_from_page_text(
                    page, community_name, community_address
                )

        except Exception as e:
            self.logger.warning(f"Error extracting listings: {e}")

        return listings

    async def _parse_pricing_row(
        self,
        row,
        community_name: str,
        community_address: str,
        page_url: str,
    ) -> Optional[ListingData]:
        """Parse a pricing table row.

        Expected format: Building/Unit | Term | Price | Available | Features | Map
        """
        try:
            text = await row.inner_text()

            # Skip header rows
            if 'BLDG NO' in text.upper() or 'PRICE' in text.upper() and 'TERM' in text.upper():
                return None

            # Extract price
            price_match = re.search(r'\$[\d,]+', text)
            if not price_match:
                return None
            price = Decimal(price_match.group().replace('$', '').replace(',', ''))

            # Skip if price is too low (likely not a unit listing)
            if price < 1000:
                return None

            # Extract unit number (format: "04 256" or similar)
            unit_match = re.search(r'\b(\d{1,2}\s+\d{2,4})\b', text)
            if unit_match:
                unit_number = unit_match.group(1).replace(' ', '-')
            else:
                # Try alternate format
                unit_match = re.search(r'(?:apt|unit|#)\s*(\d+)', text, re.I)
                unit_number = unit_match.group(1) if unit_match else "Unknown"

            # Extract available date
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
            available_date = None
            if date_match:
                try:
                    available_date = datetime.strptime(date_match.group(1), "%m/%d/%Y")
                except ValueError:
                    pass

            # Extract floor
            floor_match = re.search(r'(\d+)(?:st|nd|rd|th)\s*[Ff]loor', text)
            floor = int(floor_match.group(1)) if floor_match else None

            # Try to find bedroom/bathroom info nearby
            # Default to 1BR/1BA, actual values come from floor plan section
            bedrooms = 1
            bathrooms = 1
            sqft = 700  # Default estimate

            beds_match = re.search(r'(\d+)\s*(?:bed|br)', text, re.I)
            if beds_match:
                bedrooms = int(beds_match.group(1))

            baths_match = re.search(r'(\d+)\s*(?:bath|ba)', text, re.I)
            if baths_match:
                bathrooms = int(baths_match.group(1))

            sqft_match = re.search(r'(\d{3,4})\s*(?:sf|sq)', text, re.I)
            if sqft_match:
                sqft = int(sqft_match.group(1))

            return ListingData(
                community_name=community_name,
                address=community_address,
                unit_number=unit_number,
                price=price,
                bedrooms=bedrooms,
                bathrooms=bathrooms,
                sqft=sqft,
                floor=floor,
                available_date=available_date,
                listing_url=page_url,
            )

        except Exception as e:
            self.logger.debug(f"Error parsing row: {e}")
            return None

    async def _extract_from_page_text(
        self,
        page: Page,
        community_name: str,
        community_address: str,
    ) -> list[ListingData]:
        """Extract listings from the full page text content."""
        listings: list[ListingData] = []

        try:
            # Get the main content area
            content = await page.query_selector('main, .fapt-fp-list, #main-content')
            if not content:
                content = await page.query_selector('body')

            if not content:
                return listings

            text = await content.inner_text()

            # Split by price pattern to identify individual units
            # Pattern: price followed by date
            unit_pattern = r'(\$[\d,]+)\s+(\d{1,2}/\d{1,2}/\d{4})'
            matches = list(re.finditer(unit_pattern, text))

            self.logger.info(f"Found {len(matches)} potential units via price pattern")

            # For each match, extract surrounding context
            for i, match in enumerate(matches):
                try:
                    price_str = match.group(1)
                    date_str = match.group(2)

                    price = Decimal(price_str.replace('$', '').replace(',', ''))

                    # Skip unreasonable prices
                    if price < 2000 or price > 10000:
                        continue

                    # Get context before this match (for unit number)
                    start_pos = max(0, match.start() - 50)
                    context_before = text[start_pos:match.start()]

                    # Get context after (for floor info)
                    end_pos = min(len(text), match.end() + 100)
                    context_after = text[match.end():end_pos]

                    # Extract unit number from context before
                    unit_match = re.search(r'(\d{1,2}\s+\d{2,4})', context_before)
                    unit_number = unit_match.group(1).replace(' ', '-') if unit_match else f"Unit-{i+1}"

                    # Extract floor from context after
                    floor_match = re.search(r'(\d+)(?:st|nd|rd|th)\s*[Ff]loor', context_after)
                    floor = int(floor_match.group(1)) if floor_match else None

                    # Parse date
                    available_date = None
                    try:
                        available_date = datetime.strptime(date_str, "%m/%d/%Y")
                    except ValueError:
                        pass

                    listing = ListingData(
                        community_name=community_name,
                        address=community_address,
                        unit_number=unit_number,
                        price=price,
                        bedrooms=1,  # Default, will be updated by floor plan context
                        bathrooms=1,
                        sqft=700,
                        floor=floor,
                        available_date=available_date,
                        listing_url=page.url,
                    )
                    listings.append(listing)

                except Exception as e:
                    self.logger.debug(f"Error extracting unit {i}: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"Error in text extraction: {e}")

        return listings
