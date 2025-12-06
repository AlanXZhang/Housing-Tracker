"""Irvine Company Apartments scraper - Enhanced data extraction."""

import math
import re
from datetime import datetime
from decimal import Decimal
from typing import Optional

from playwright.async_api import Page

from apartment_tracker.models.schemas import ListingData
from apartment_tracker.scrapers.base import BaseScraper


class IrvineCompanyScraper(BaseScraper):
    """Scraper for Irvine Company Apartment Homes websites.

    Enhanced to extract:
    - Floor plan info (beds, baths, sqft range → use minimum)
    - Lease term
    - Features
    - Floor plan image URL
    - Map position (via View on Map click)
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

            # First, extract floor plan info (beds, baths, sqft) for each plan
            floor_plan_info = await self._extract_floor_plan_info(page)
            self.logger.info(f"Extracted info for {len(floor_plan_info)} floor plans")

            # Click all expand buttons to reveal unit data
            await self._expand_all_floor_plans(page)

            # Wait for all content to load
            await page.wait_for_timeout(2000)

            # Extract listings with enhanced data
            listings = await self._extract_all_listings(
                page, community_name, community_address, floor_plan_info
            )

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
            address_el = await page.query_selector('.fapt-community-contact__address, address')
            if address_el:
                text = await address_el.inner_text()
                if text:
                    return text.strip().replace('\n', ', ')
        except Exception:
            pass
        return "Santa Clara, CA"

    async def _extract_floor_plan_info(self, page: Page) -> dict:
        """Extract floor plan info (beds, baths, sqft) before expanding.

        Returns a dict mapping floor plan name to {bedrooms, bathrooms, sqft, image_url}.
        """
        floor_plans = {}

        try:
            # Get all floor plan items
            items = await page.query_selector_all('.fapt-fp-list-item')

            for item in items:
                try:
                    text = await item.inner_text()

                    # Extract floor plan name (like "PLAN 01", "PLAN 04B", "PLAN 30 Alt")
                    name_match = re.search(r'(PLAN\s+\d+[A-Z]?(?:\s+Alt)?)', text, re.I)
                    plan_name = name_match.group(1).upper() if name_match else None

                    if not plan_name:
                        continue

                    # Parse bedrooms and bathrooms from format like:
                    # "Studio / 1 Bath", "1 Bed / 1 Bath", "Den / 1 Bed / 1 Bath"
                    # "Loft / 2 Bed / 2 Bath", "Loft / Studio / 1 Bath", "Townhome / 2 Bed / 2 Bath"
                    text_upper = text.upper()

                    # Base bedrooms count
                    if 'STUDIO' in text_upper:
                        bedrooms = 0.0
                    else:
                        beds_match = re.search(r'(\d+)\s*(?:Bed|BR)', text, re.I)
                        bedrooms = float(beds_match.group(1)) if beds_match else 1.0

                    # Add 0.5 for Den or Loft prefix
                    # "Den / 1 Bed" = 1.5, "Loft / 2 Bed" = 2.5, "Loft / Studio" = 0.5
                    if 'DEN' in text_upper or 'LOFT' in text_upper:
                        bedrooms += 0.5

                    # Parse bathrooms
                    baths_match = re.search(r'(\d+)\s*(?:Bath|BA)', text, re.I)
                    bathrooms = float(baths_match.group(1)) if baths_match else 1.0
                    # Note: Half baths would need additional parsing if present

                    # Parse sqft - order in card is usually: Bed/Bath → Price → Sqft
                    # But for "No Availability" plans, there's no price, just: Bed/Bath → "No Availability" → Sqft
                    # Format can be "640 - 642" or "1,067 - 1,123" (with commas)
                    sqft = 0

                    # Try 1: Look after price pattern (for available plans)
                    price_pattern = re.search(r'\$[\d,]+', text)
                    if price_pattern:
                        after_price = text[price_pattern.end():]
                        sqft_match = re.search(r'([\d,]{3,5})\s*(?:-\s*([\d,]{3,5}))?', after_price)
                        if sqft_match:
                            potential_sqft = int(sqft_match.group(1).replace(',', ''))
                            if 400 <= potential_sqft <= 3000:
                                sqft = potential_sqft

                    # Try 2: Fallback for "No Availability" plans - look after bed/bath pattern
                    if sqft == 0:
                        bedbath_match = re.search(r'(?:Studio|Bed)\s*/\s*\d+\s*Baths?', text, re.I)
                        if bedbath_match:
                            after_bedbath = text[bedbath_match.end():]
                            # Skip "No Availability" text if present, then find sqft
                            sqft_match = re.search(r'([\d,]{3,5})\s*(?:-\s*([\d,]{3,5}))?', after_bedbath)
                            if sqft_match:
                                potential_sqft = int(sqft_match.group(1).replace(',', ''))
                                if 400 <= potential_sqft <= 3000:
                                    sqft = potential_sqft

                    # Try to find floor plan image URL
                    image_url = None
                    img_el = await item.query_selector('img')
                    if img_el:
                        image_url = await img_el.get_attribute('src')

                    floor_plans[plan_name] = {
                        "bedrooms": bedrooms,
                        "bathrooms": bathrooms,
                        "sqft": sqft,
                        "image_url": image_url,
                    }

                    self.logger.debug(f"Floor plan {plan_name}: {bedrooms}BR/{bathrooms}BA, {sqft} sqft")

                except Exception as e:
                    self.logger.debug(f"Error parsing floor plan: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"Error extracting floor plan info: {e}")

        return floor_plans

    async def _expand_all_floor_plans(self, page: Page) -> None:
        """Click all expand buttons to reveal unit data."""
        expand_buttons = await page.query_selector_all(
            'button[aria-expanded="false"], '
            '.fapt-fp-list-item__acc-trigger-cta'
        )

        self.logger.info(f"Found {len(expand_buttons)} expand buttons to click")

        for i, button in enumerate(expand_buttons):
            try:
                is_expanded = await button.get_attribute('aria-expanded')
                if is_expanded == 'true':
                    continue

                await button.click()
                await page.wait_for_timeout(500)

            except Exception as e:
                self.logger.debug(f"Could not click button {i}: {e}")
                continue

        await page.wait_for_timeout(2000)

    async def _extract_all_listings(
        self,
        page: Page,
        community_name: str,
        community_address: str,
        floor_plan_info: dict,
    ) -> list[ListingData]:
        """Extract all listings from the fully expanded page."""
        listings: list[ListingData] = []

        try:
            # Get all floor plan sections for context
            sections = await page.query_selector_all('.fapt-fp-list-item')

            for section in sections:
                try:
                    section_text = await section.inner_text()

                    # Get floor plan name for this section (like "PLAN 30", "PLAN 30 Alt")
                    plan_match = re.search(r'(PLAN\s+\d+[A-Z]?(?:\s+Alt)?)', section_text, re.I)
                    plan_name = plan_match.group(1).upper() if plan_match else None

                    # Get floor plan details
                    plan_info = floor_plan_info.get(plan_name, {})

                    # Extract units from this section
                    section_listings = self._parse_section_units(
                        section_text,
                        plan_name,
                        plan_info,
                        community_name,
                        community_address,
                        page.url,
                    )
                    listings.extend(section_listings)

                except Exception as e:
                    self.logger.debug(f"Error processing section: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"Error extracting listings: {e}")

        # Deduplicate by unit number
        seen = set()
        unique_listings = []
        for listing in listings:
            if listing.unit_number not in seen:
                seen.add(listing.unit_number)
                unique_listings.append(listing)

        return unique_listings

    def _parse_section_units(
        self,
        section_text: str,
        plan_name: Optional[str],
        plan_info: dict,
        community_name: str,
        community_address: str,
        page_url: str,
    ) -> list[ListingData]:
        """Parse all units from a floor plan section's text."""
        units: list[ListingData] = []

        # Pattern to match unit rows:
        # Building/Unit (like "04 256"), optional term, Price, Date, Features
        # Example: "04 256 13 mo. $3,095 01/26/2026 2nd Floor, Courtyard view"

        # Find all price + date patterns
        pattern = r'(\d{1,2}\s+\d{2,4})\s+(\d+\s*mo\.?)\s+\$?([\d,]+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+([^\$]+?)(?=\d{1,2}\s+\d{2,4}\s+\d+\s*mo|VIEW ON MAP|APPLY NOW|$)'

        matches = list(re.finditer(pattern, section_text, re.I))

        if not matches:
            # Fallback: simpler pattern
            simple_pattern = r'\$?([\d,]+)\s+(\d{1,2}/\d{1,2}/\d{4})'
            for match in re.finditer(simple_pattern, section_text):
                try:
                    price = Decimal(match.group(1).replace(',', ''))
                    if price < 2000 or price > 10000:
                        continue

                    date_str = match.group(2)

                    # Find unit number before this price
                    before_text = section_text[:match.start()]
                    unit_match = re.search(r'(\d{1,2}\s+\d{2,4})\s*(?:\d+\s*mo\.?)?\s*$', before_text)
                    unit_number = unit_match.group(1).replace(' ', '-') if unit_match else None

                    if not unit_number:
                        continue

                    # Find lease term
                    term_match = re.search(r'(\d+)\s*mo\.?', before_text[-30:])
                    lease_term = int(term_match.group(1)) if term_match else None

                    # Find floor and features after the date
                    after_text = section_text[match.end():match.end() + 150]
                    floor_match = re.search(r'(\d+)(?:st|nd|rd|th)\s*[Ff]loor', after_text)
                    floor = int(floor_match.group(1)) if floor_match else None

                    # Extract features
                    features = self._extract_features(after_text)

                    # Parse date with year
                    available_date = self._parse_date_with_year(date_str)

                    listing = ListingData(
                        community_name=community_name,
                        address=community_address,
                        unit_number=unit_number,
                        price=int(math.ceil(float(price))),
                        bedrooms=float(plan_info.get("bedrooms", 1.0)),
                        bathrooms=float(plan_info.get("bathrooms", 1.0)),
                        sqft=plan_info.get("sqft", 0),
                        floor=floor,
                        floor_plan_name=plan_name,
                        floor_plan_image_url=plan_info.get("image_url"),
                        available_date=available_date,
                        lease_term_months=lease_term,
                        features=features,
                        listing_url=page_url,
                    )
                    units.append(listing)

                except Exception:
                    continue

        else:
            for match in matches:
                try:
                    unit_number = match.group(1).replace(' ', '-')
                    lease_term_str = match.group(2)
                    price = Decimal(match.group(3).replace(',', ''))
                    date_str = match.group(4)
                    features_text = match.group(5)

                    if price < 2000 or price > 10000:
                        continue

                    # Parse lease term
                    term_match = re.search(r'(\d+)', lease_term_str)
                    lease_term = int(term_match.group(1)) if term_match else None

                    # Parse floor from features
                    floor_match = re.search(r'(\d+)(?:st|nd|rd|th)\s*[Ff]loor', features_text)
                    floor = int(floor_match.group(1)) if floor_match else None

                    # Extract features list
                    features = self._extract_features(features_text)

                    # Parse date with year
                    available_date = self._parse_date_with_year(date_str)

                    listing = ListingData(
                        community_name=community_name,
                        address=community_address,
                        unit_number=unit_number,
                        price=int(math.ceil(float(price))),
                        bedrooms=float(plan_info.get("bedrooms", 1.0)),
                        bathrooms=float(plan_info.get("bathrooms", 1.0)),
                        sqft=plan_info.get("sqft", 0),
                        floor=floor,
                        floor_plan_name=plan_name,
                        floor_plan_image_url=plan_info.get("image_url"),
                        available_date=available_date,
                        lease_term_months=lease_term,
                        features=features,
                        listing_url=page_url,
                    )
                    units.append(listing)

                except Exception as e:
                    self.logger.debug(f"Error parsing unit: {e}")
                    continue

        return units

    def _extract_features(self, text: str) -> list[str]:
        """Extract feature list from text."""
        features = []

        # Common features to look for
        feature_patterns = [
            r'(\d+(?:st|nd|rd|th)\s*[Ff]loor)',
            r'(Courtyard\s*view)',
            r'(Pool\s*view)',
            r'(Street\s*view)',
            r'(Corner\s*unit)',
            r'(Balcony)',
            r'(Patio)',
            r'(Updated)',
            r'(Renovated)',
        ]

        for pattern in feature_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                features.append(match.group(1).strip())

        return features

    def _parse_date_with_year(self, date_str: str) -> Optional[datetime]:
        """Parse date string with full year (MM/DD/YYYY format)."""
        if not date_str:
            return None

        date_str = date_str.strip()

        formats = [
            "%m/%d/%Y",   # 01/26/2026
            "%m/%d/%y",   # 01/26/26
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    async def get_unit_map_position(self, page: Page, unit_number: str) -> Optional[dict]:
        """Click 'View on Map' for a unit to get its position.

        Returns dict with position info for direction detection.
        """
        try:
            # Find the row containing this unit
            unit_pattern = unit_number.replace('-', ' ')

            # Look for VIEW ON MAP button near this unit
            buttons = await page.query_selector_all('button, a')

            for button in buttons:
                text = await button.inner_text()
                if 'VIEW ON MAP' in text.upper():
                    # Check if this button is near our unit
                    parent = await button.evaluate_handle('el => el.closest(".fapt-fp-pricing-table__row")')
                    if parent:
                        row_text = await parent.inner_text()
                        if unit_pattern in row_text:
                            # Click to open map
                            await button.click()
                            await page.wait_for_timeout(2000)

                            # Try to capture the map state
                            # The map should highlight this unit's position
                            map_screenshot = await self.take_screenshot(
                                page, f"unit_map_{unit_number}"
                            )

                            # Close the map modal if there is one
                            close_button = await page.query_selector(
                                '[aria-label="Close"], .modal-close, .close-button'
                            )
                            if close_button:
                                await close_button.click()
                                await page.wait_for_timeout(500)

                            return {
                                "unit_number": unit_number,
                                "map_screenshot": map_screenshot,
                            }

        except Exception as e:
            self.logger.warning(f"Error getting map position for {unit_number}: {e}")

        return None
