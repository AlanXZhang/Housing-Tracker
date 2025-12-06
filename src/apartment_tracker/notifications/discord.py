"""Discord notification sender."""

import logging
from typing import Optional

import httpx

from apartment_tracker.models.schemas import FilterResult, ListingData, NotificationPayload

logger = logging.getLogger(__name__)


class DiscordNotifier:
    """Send notifications via Discord webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, payload: NotificationPayload) -> bool:
        """Send a notification for a listing.

        Args:
            payload: The notification payload with listing and filter info.

        Returns:
            True if sent successfully, False otherwise.
        """
        try:
            embed = self._build_embed(payload)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={"embeds": [embed]},
                    timeout=10.0,
                )
                response.raise_for_status()

            logger.info(f"Discord notification sent for {payload.listing.unit_number}")
            return True

        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False

    async def send_batch(self, payloads: list[NotificationPayload]) -> dict:
        """Send multiple notifications.

        Args:
            payloads: List of notification payloads.

        Returns:
            Dict with 'sent' and 'failed' counts.
        """
        sent = 0
        failed = 0

        for payload in payloads:
            if await self.send(payload):
                sent += 1
            else:
                failed += 1

        return {"sent": sent, "failed": failed}

    def _build_embed(self, payload: NotificationPayload) -> dict:
        """Build a Discord embed for a listing notification."""
        listing = payload.listing
        result = payload.filter_result

        # Determine color based on notification type
        if payload.price_changed:
            color = 0xFFA500  # Orange for price change
            title_prefix = "💰 Price Change"
        else:
            color = 0x00FF00  # Green for new listing
            title_prefix = "🏠 New Match"

        title = f"{title_prefix}: {listing.community_name} - ${listing.price:,.0f}/mo"

        # Build fields
        fields = [
            {
                "name": "📍 Address",
                "value": f"{listing.address}\nUnit {listing.unit_number}",
                "inline": False,
            },
            {
                "name": "💰 Price",
                "value": f"${listing.price:,.0f}/month",
                "inline": True,
            },
            {
                "name": "📐 Size",
                "value": f"{listing.sqft:,} sqft",
                "inline": True,
            },
            {
                "name": "🛏️ Layout",
                "value": f"{listing.bedrooms}BR/{listing.bathrooms}BA",
                "inline": True,
            },
        ]

        # Add floor if available
        if listing.floor:
            fields.append({
                "name": "🏢 Floor",
                "value": str(listing.floor),
                "inline": True,
            })

        # Add direction if available
        if listing.facing_direction:
            direction_emoji = "🧭"
            if listing.facing_direction.upper() in ["S", "SW"]:
                direction_emoji = "☀️"  # Sun for preferred directions
            fields.append({
                "name": f"{direction_emoji} Direction",
                "value": listing.facing_direction,
                "inline": True,
            })

        # Add available date if present
        if listing.available_date:
            fields.append({
                "name": "📅 Available",
                "value": listing.available_date.strftime("%b %d, %Y"),
                "inline": True,
            })

        # Add score
        fields.append({
            "name": "🎯 Match Score",
            "value": f"{result.score} points",
            "inline": True,
        })

        # Add price change info if applicable
        if payload.price_changed and payload.previous_price:
            diff = listing.price - payload.previous_price
            direction = "📈" if diff > 0 else "📉"
            fields.append({
                "name": f"{direction} Price Change",
                "value": f"${payload.previous_price:,.0f} → ${listing.price:,.0f} ({'+' if diff > 0 else ''}{diff:,.0f})",
                "inline": False,
            })

        embed = {
            "title": title,
            "color": color,
            "fields": fields,
            "url": listing.listing_url,
            "footer": {
                "text": "Apartment Tracker | Click title to view listing",
            },
        }

        return embed


async def send_discord_notification(
    webhook_url: str,
    listing: ListingData,
    filter_result: FilterResult,
    is_new: bool = True,
    previous_price: Optional[float] = None,
) -> bool:
    """Convenience function to send a Discord notification.

    Args:
        webhook_url: Discord webhook URL.
        listing: The listing to notify about.
        filter_result: The filter result for the listing.
        is_new: Whether this is a new listing.
        previous_price: Previous price if this is a price change.

    Returns:
        True if sent successfully.
    """
    notifier = DiscordNotifier(webhook_url)
    payload = NotificationPayload(
        listing=listing,
        filter_result=filter_result,
        is_new=is_new,
        price_changed=previous_price is not None,
        previous_price=previous_price,
    )
    return await notifier.send(payload)
