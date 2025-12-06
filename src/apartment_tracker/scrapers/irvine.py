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

    Irvine Company uses a JavaScript-heavy site with expandable floor plan cards.
    Each floor plan must be clicked to reveal individual units.

    Example URL:
    https://www.irvinecompanyapartments.com/locations/northern-california/santa-clara/santa-clara-square/availability.html
    """

    MANAGEMENT_COMPANY = "irvine"
    BASE_URL = "https://www.irvinecompanyapartments.com"

    async def scrape_availability(self, url: str) -> list[ListingData]:
        """Scrape all available listings from an Irvine Company availability page.

        Args:
            url: The availability page URL (e.g., .../availability.html)

        Returns:
            List of ListingData objects for available units.
        """
        page = await self.new_page()
        try:
            if not await self.safe_navigate(page, url):
                return []

            # Wait for the page to load
            await page.wait_for_timeout(3000)

            # Get community info
            community_name = await self.get_community_name(page)
            community_address = await self.get_community_address(page)

            self.logger.info(f"Scraping {community_name} at {community_address}")

            # Extract all listings by expanding each floor plan
            listings = await self._extract_listings(page, community_name, community_address)

            self.logger.info(f"Found {len(listings)} listings at {community_name}")
            return listings

        finally:
            await page.close()

    async def get_community_name(self, page: Page) -> str:
        """Extract the community name from the page."""
        # Try the title first
        title = await page.title()
        if title:
            # Format: "Apartment Availability in Santa Clara | Santa Clara Square"
            parts = title.split('|')
            if len(parts) > 1:
                return parts[-1].strip()

        # Try meta tag
        try:
            meta = await page.query_selector('meta[property="og:site_name"]')
            if meta:
                content = await meta.get_attribute('content')
                if content:
                    return content.strip()
        except Exception:
            pass

        return "Unknown Community"

    async def get_community_address(self, page: Page) -> str:
        """Extract the community address from the page."""
        # Try to find address in the page
        selectors = [
            '.fapt-community-contact__address',
            '[data-testid="community-address"]',
            '.community-address',
            'address',
        ]

        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text:
                        return text.strip().replace('\n', ', ')
            except Exception:
                continue

        # Try to extract from footer or contact section
        try:
            footer = await page.query_selector('.fapt-community-contact')
            if footer:
                text = await footer.inner_text()
                # Try to find address pattern
                lines = text.split('\n')
                for line in lines:
                    if re.search(r'\d{5}', line):  # Has zip code
                        return line.strip()
        except Exception:
            pass

        return "Santa Clara, CA"  # Default for this community

    async def _extract_listings(
        self,
        page: Page,
        community_name: str,
        community_address: str,
    ) -> list[ListingData]:
        """Extract all listings by expanding floor plan cards."""
        listings: list[ListingData] = []

        # Find all floor plan accordion items
        # The expand buttons have class like 'fapt-fp-list-item__acc-trigger-cta'
        expand_buttons = await page.query_selector_all(
            'button.fapt-fp-list-item__acc-trigger-cta, '
            '.fapt-fp-list-item button[aria-expanded], '
            '.floor-plan-card button.expand'
        )

        self.logger.info(f"Found {len(expand_buttons)} floor plan sections")

        if not expand_buttons:
            # Try alternate approach - maybe listings are already visible
            self.logger.info("No expand buttons found, trying direct extraction")
            return await self._extract_visible_listings(page, community_name, community_address)

        # Click each expand button and extract units
        for i, button in enumerate(expand_buttons):
            try:
                # Get floor plan info before clicking
                floor_plan_card = await button.evaluate_handle(
                    'el => el.closest(".fapt-fp-list-item") || el.closest(".floor-plan-card")'
                )

                floor_plan_name = await self._get_floor_plan_name(floor_plan_card)
                floor_plan_info = await self._get_floor_plan_info(floor_plan_card)

                self.logger.debug(f"Expanding floor plan {i+1}: {floor_plan_name}")

                # Click to expand
                await button.click()
                await page.wait_for_timeout(1500)  # Wait for animation + data load

                # Extract units from the expanded section
                units = await self._extract_units_from_expanded(
                    page, floor_plan_card, floor_plan_name, floor_plan_info,
                    community_name, community_address
                )
                listings.extend(units)

                self.logger.debug(f"Found {len(units)} units in {floor_plan_name}")

            except Exception as e:
                self.logger.warning(f"Error processing floor plan {i+1}: {e}")
                continue

        return listings

    async def _get_floor_plan_name(self, card) -> str:
        """Get the floor plan name from a card element."""
        if not card:
            return "Unknown"

        selectors = [
            '.fapt-fp-list-item__name',
            '.floor-plan-name',
            'h3',
            'h4',
        ]

        for selector in selectors:
            try:
                el = await card.query_selector(selector)
                if el:
                    text = await el.inner_text()
                    if text:
                        return text.strip()
            except Exception:
                continue

        return "Unknown"

    async def _get_floor_plan_info(self, card) -> dict:
        """Extract beds, baths, sqft from floor plan card header."""
        info = {"bedrooms": 1, "bathrooms": 1, "sqft": 0}

        if not card:
            return info

        try:
            # Try to find specs text like "1 Bed / 1 Bath / 675 - 721 SF"
            text = await card.inner_text()

            # Parse bedrooms
            beds_match = re.search(r'(\d+)\s*(?:Bed|BR)', text, re.I)
            if beds_match:
                info["bedrooms"] = int(beds_match.group(1))

            # Parse bathrooms
            baths_match = re.search(r'(\d+)\s*(?:Bath|BA)', text, re.I)
            if baths_match:
                info["bathrooms"] = int(baths_match.group(1))

            # Parse sqft - might be a range like "675 - 721 SF"
            sqft_match = re.search(r'(\d{3,4})\s*(?:-\s*\d{3,4})?\s*(?:SF|sq\.?\s*ft)', text, re.I)
            if sqft_match:
                info["sqft"] = int(sqft_match.group(1))

        except Exception:
            pass

        return info

    async def _extract_units_from_expanded(
        self,
        page: Page,
        floor_plan_card,
        floor_plan_name: str,
        floor_plan_info: dict,
        community_name: str,
        community_address: str,
    ) -> list[ListingData]:
        """Extract unit listings from an expanded floor plan section."""
        units: list[ListingData] = []

        # After expanding, look for unit rows
        # The structure shows data like: "04 256", "13 mo.", "$3,095", "01/26/2026", "2nd Floor", etc.
        try:
            # Find the expanded content area
            content_selectors = [
                '.fapt-fp-pricing-table',
                '.fapt-fp-list-item__content',
                '.units-table',
                '[class*="expanded"]',
                '[aria-expanded="true"] + *',
            ]

            content_area = None
            for selector in content_selectors:
                content_area = await page.query_selector(selector)
                if content_area:
                    break

            if not content_area:
                # Try to find within the card itself
                if floor_plan_card:
                    content_area = floor_plan_card

            if not content_area:
                return units

            # Try to find unit rows
            row_selectors = [
                '.fapt-fp-pricing-table__row',
                'tr.unit-row',
                '[class*="unit-row"]',
                '.apartment-row',
            ]

            rows = []
            for selector in row_selectors:
                rows = await content_area.query_selector_all(selector)
                if rows:
                    break

            # If no structured rows, try to parse text content
            if not rows:
                text_content = await content_area.inner_text()
                units = self._parse_text_content(
                    text_content, floor_plan_name, floor_plan_info,
                    community_name, community_address, page.url
                )
                return units

            # Parse structured rows
            for row in rows:
                try:
                    unit = await self._parse_unit_row(
                        row, floor_plan_name, floor_plan_info,
                        community_name, community_address, page.url
                    )
                    if unit:
                        units.append(unit)
                except Exception as e:
                    self.logger.warning(f"Error parsing unit row: {e}")

        except Exception as e:
            self.logger.warning(f"Error extracting units: {e}")

        return units

    async def _parse_unit_row(
        self,
        row,
        floor_plan_name: str,
        floor_plan_info: dict,
        community_name: str,
        community_address: str,
        page_url: str,
    ) -> Optional[ListingData]:
        """Parse a single unit row element."""
        try:
            text = await row.inner_text()
            return self._parse_unit_text(
                text, floor_plan_name, floor_plan_info,
                community_name, community_address, page_url
            )
        except Exception:
            return None

    def _parse_text_content(
        self,
        text: str,
        floor_plan_name: str,
        floor_plan_info: dict,
        community_name: str,
        community_address: str,
        page_url: str,
    ) -> list[ListingData]:
        """Parse unit data from raw text content."""
        units: list[ListingData] = []

        # Look for patterns like:
        # Unit/Building number, Term, Price, Available date, Floor, Features
        # Example: "04 256" "13 mo." "$3,095" "01/26/2026" "2nd Floor" "Courtyard view"

        # Find all price patterns
        price_pattern = r'\$[\d,]+'
        prices = re.findall(price_pattern, text)

        # Find unit/building patterns (like "04 256" or "#305")
        unit_pattern = r'(?:(?:\d{1,2}\s+\d{2,4})|(?:#?\d{3,4}))'
        unit_matches = re.findall(unit_pattern, text)

        # Find dates
        date_pattern = r'\d{1,2}/\d{1,2}/\d{2,4}'
        dates = re.findall(date_pattern, text)

        # Find floor mentions
        floor_pattern = r'(\d+)(?:st|nd|rd|th)\s*[Ff]loor'
        floors = re.findall(floor_pattern, text)

        # Try to match them up (this is imperfect but a starting point)
        for i, price_str in enumerate(prices):
            try:
                price = Decimal(price_str.replace('$', '').replace(',', ''))

                unit_number = unit_matches[i] if i < len(unit_matches) else f"Unit {i+1}"
                floor = int(floors[i]) if i < len(floors) else None

                available_date = None
                if i < len(dates):
                    try:
                        available_date = datetime.strptime(dates[i], "%m/%d/%Y")
                    except ValueError:
                        pass

                # Get sqft from floor plan info or estimate
                sqft = floor_plan_info.get("sqft", 700)
                if sqft == 0:
                    sqft = 700  # Default estimate

                unit = ListingData(
                    community_name=community_name,
                    address=community_address,
                    unit_number=unit_number.replace(' ', '-'),
                    price=price,
                    bedrooms=floor_plan_info.get("bedrooms", 1),
                    bathrooms=floor_plan_info.get("bathrooms", 1),
                    sqft=sqft,
                    floor=floor,
                    floor_plan_name=floor_plan_name,
                    available_date=available_date,
                    listing_url=page_url,
                )
                units.append(unit)

            except Exception as e:
                self.logger.debug(f"Error parsing unit from text: {e}")
                continue

        return units

    def _parse_unit_text(
        self,
        text: str,
        floor_plan_name: str,
        floor_plan_info: dict,
        community_name: str,
        community_address: str,
        page_url: str,
    ) -> Optional[ListingData]:
        """Parse a single unit from text."""
        try:
            # Find price
            price_match = re.search(r'\$[\d,]+', text)
            if not price_match:
                return None
            price = Decimal(price_match.group().replace('$', '').replace(',', ''))

            # Find unit number
            unit_match = re.search(r'(?:\d{1,2}\s+\d{2,4})|(?:#?\d{3,4})', text)
            unit_number = unit_match.group().replace(' ', '-') if unit_match else "Unknown"

            # Find floor
            floor_match = re.search(r'(\d+)(?:st|nd|rd|th)\s*[Ff]loor', text)
            floor = int(floor_match.group(1)) if floor_match else None

            # Find date
            date_match = re.search(r'\d{1,2}/\d{1,2}/\d{2,4}', text)
            available_date = None
            if date_match:
                try:
                    available_date = datetime.strptime(date_match.group(), "%m/%d/%Y")
                except ValueError:
                    pass

            # Get sqft
            sqft = floor_plan_info.get("sqft", 700)
            if sqft == 0:
                sqft = 700

            return ListingData(
                community_name=community_name,
                address=community_address,
                unit_number=unit_number,
                price=price,
                bedrooms=floor_plan_info.get("bedrooms", 1),
                bathrooms=floor_plan_info.get("bathrooms", 1),
                sqft=sqft,
                floor=floor,
                floor_plan_name=floor_plan_name,
                available_date=available_date,
                listing_url=page_url,
            )

        except Exception:
            return None

    async def _extract_visible_listings(
        self,
        page: Page,
        community_name: str,
        community_address: str,
    ) -> list[ListingData]:
        """Fallback: Try to extract any visible listings without expanding."""
        listings: list[ListingData] = []

        # Get all text from the availability section
        try:
            content = await page.query_selector('.fapt-fp-list, .availability-container, main')
            if content:
                text = await content.inner_text()
                # Use the text parsing method
                listings = self._parse_text_content(
                    text, "Unknown", {"bedrooms": 1, "bathrooms": 1, "sqft": 700},
                    community_name, community_address, page.url
                )
        except Exception as e:
            self.logger.warning(f"Fallback extraction failed: {e}")

        return listings
