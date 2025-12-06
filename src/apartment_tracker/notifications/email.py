"""Email notification sender with optional digest mode."""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from apartment_tracker.models.schemas import FilterResult, ListingData, NotificationPayload

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Send notifications via email (SMTP or SendGrid)."""

    def __init__(
        self,
        provider: str = "smtp",
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        sendgrid_api_key: Optional[str] = None,
        recipients: Optional[list[str]] = None,
    ):
        self.provider = provider.lower()
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.sendgrid_api_key = sendgrid_api_key
        self.recipients = recipients or []

    async def send(self, payload: NotificationPayload) -> bool:
        """Send a notification for a single listing.

        Args:
            payload: The notification payload.

        Returns:
            True if sent successfully.
        """
        subject = self._build_subject(payload)
        html_body = self._build_html_body([payload])

        return await self._send_email(subject, html_body)

    async def send_digest(self, payloads: list[NotificationPayload]) -> bool:
        """Send a digest email with multiple listings.

        Args:
            payloads: List of notification payloads.

        Returns:
            True if sent successfully.
        """
        if not payloads:
            return True  # Nothing to send

        subject = f"🏠 Apartment Digest: {len(payloads)} New Matches"
        html_body = self._build_html_body(payloads)

        return await self._send_email(subject, html_body)

    async def _send_email(self, subject: str, html_body: str) -> bool:
        """Send an email via configured provider."""
        if not self.recipients:
            logger.warning("No email recipients configured")
            return False

        try:
            if self.provider == "smtp":
                return await self._send_smtp(subject, html_body)
            elif self.provider == "sendgrid":
                return await self._send_sendgrid(subject, html_body)
            else:
                logger.error(f"Unknown email provider: {self.provider}")
                return False

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def _send_smtp(self, subject: str, html_body: str) -> bool:
        """Send via SMTP."""
        if not self.username or not self.password:
            logger.error("SMTP username and password required")
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.username
        msg["To"] = ", ".join(self.recipients)

        # Attach HTML body
        msg.attach(MIMEText(html_body, "html"))

        # Send via SMTP
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.username, self.recipients, msg.as_string())

        logger.info(f"Email sent to {len(self.recipients)} recipients")
        return True

    async def _send_sendgrid(self, subject: str, html_body: str) -> bool:
        """Send via SendGrid API."""
        if not self.sendgrid_api_key:
            logger.error("SendGrid API key required")
            return False

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={
                        "Authorization": f"Bearer {self.sendgrid_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "personalizations": [{"to": [{"email": r} for r in self.recipients]}],
                        "from": {"email": self.username or "noreply@apartment-tracker.local"},
                        "subject": subject,
                        "content": [{"type": "text/html", "value": html_body}],
                    },
                    timeout=10.0,
                )
                response.raise_for_status()

            logger.info(f"SendGrid email sent to {len(self.recipients)} recipients")
            return True

        except Exception as e:
            logger.error(f"SendGrid failed: {e}")
            return False

    def _build_subject(self, payload: NotificationPayload) -> str:
        """Build email subject line."""
        listing = payload.listing
        if payload.price_changed:
            return f"💰 Price Change: {listing.community_name} - ${listing.price:,.0f}/mo"
        else:
            return f"🏠 New Match: {listing.community_name} - ${listing.price:,.0f}/mo"

    def _build_html_body(self, payloads: list[NotificationPayload]) -> str:
        """Build HTML email body."""
        listings_html = ""

        for payload in payloads:
            listing = payload.listing
            result = payload.filter_result

            # Build listing block
            direction_badge = ""
            if listing.facing_direction:
                if listing.facing_direction.upper() in ["S", "SW"]:
                    direction_badge = f'<span style="background:#22c55e;color:white;padding:2px 8px;border-radius:4px;">{listing.facing_direction} ☀️</span>'
                else:
                    direction_badge = f'<span style="background:#6b7280;color:white;padding:2px 8px;border-radius:4px;">{listing.facing_direction}</span>'

            floor_info = f"Floor {listing.floor}" if listing.floor else "Floor unknown"
            available_info = listing.available_date.strftime("%b %d, %Y") if listing.available_date else "Check listing"

            listings_html += f"""
            <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:16px;background:#ffffff;">
                <h3 style="margin:0 0 8px 0;color:#1f2937;">
                    <a href="{listing.listing_url}" style="color:#2563eb;text-decoration:none;">
                        {listing.community_name} - Unit {listing.unit_number}
                    </a>
                </h3>
                <p style="margin:0 0 8px 0;color:#6b7280;">{listing.address}</p>
                <div style="display:flex;flex-wrap:wrap;gap:16px;margin-bottom:8px;">
                    <span><strong>💰 ${listing.price:,.0f}/mo</strong></span>
                    <span>🛏️ {listing.bedrooms}BR/{listing.bathrooms}BA</span>
                    <span>📐 {listing.sqft:,} sqft</span>
                    <span>🏢 {floor_info}</span>
                    <span>📅 {available_info}</span>
                </div>
                <div style="margin-top:8px;">
                    {direction_badge}
                    <span style="background:#f3f4f6;padding:2px 8px;border-radius:4px;">Score: {result.score}</span>
                </div>
            </div>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width,initial-scale=1">
        </head>
        <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f9fafb;padding:20px;">
            <div style="max-width:600px;margin:0 auto;">
                <h1 style="color:#1f2937;margin-bottom:20px;">🏠 Apartment Matches</h1>
                <p style="color:#6b7280;margin-bottom:20px;">
                    Found {len(payloads)} listing(s) matching your criteria.
                </p>
                {listings_html}
                <p style="color:#9ca3af;font-size:12px;margin-top:20px;text-align:center;">
                    Sent by Apartment Tracker • {datetime.now().strftime("%Y-%m-%d %H:%M")}
                </p>
            </div>
        </body>
        </html>
        """
