"""Main CLI entry point for Apartment Tracker."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from apartment_tracker import __version__
from apartment_tracker.config import Config, load_config
from apartment_tracker.models import (
    Listing,
    ListingData,
    PriceHistory,
    create_tables,
    get_engine,
    get_session,
)
from apartment_tracker.scrapers import get_scraper


app = typer.Typer(
    name="apartment-tracker",
    help="Monitor apartment availability and get notified when listings match your criteria.",
)
console = Console()


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> None:
    """Configure logging with rich output."""
    handlers: list[logging.Handler] = [
        RichHandler(
            console=console,
            rich_tracebacks=True,
            show_time=True,
        )
    ]

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        handlers.append(file_handler)

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=handlers,
    )


def get_database_url(config: Config) -> str:
    """Get the database URL from config."""
    if config.database.url:
        return config.database.url
    # SQLite
    db_path = Path(config.database.path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path}"


@app.command()
def version() -> None:
    """Show the version."""
    console.print(f"apartment-tracker v{__version__}")


@app.command()
def init(
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        "-c",
        help="Configuration directory",
    ),
) -> None:
    """Initialize the project with default configuration files."""
    config_dir.mkdir(parents=True, exist_ok=True)

    # Create example config
    config_file = config_dir / "config.yaml"
    if not config_file.exists():
        config_file.write_text(
            """\
# Apartment Tracker Configuration

database:
  type: sqlite
  path: ./data/apartment_tracker.db

scraping:
  interval_minutes: 30
  request_delay_seconds: 45
  max_retries: 3
  headless: true
  screenshot_on_error: true

notifications:
  discord:
    enabled: false
    # webhook_url: "https://discord.com/api/webhooks/..."

  email:
    enabled: false
    provider: smtp
    smtp_host: smtp.gmail.com
    smtp_port: 587
    # username: your-email@gmail.com
    # password: your-app-password
    recipients: []
    mode: immediate  # or 'digest'
    digest_interval_hours: 6

llm:
  provider: gemini
  # api_key: your-api-key
  model: gemini-1.5-flash

logging:
  level: INFO
  file: ./logs/scraper.log

filters:
  required:
    min_floor: 2
    min_sqft: 680
    min_bedrooms: 1
    min_bathrooms: 1
    max_price: 4699

  preferred:
    preferred_directions:
      - S
      - SW
    min_sqft_preferred: 850
    preferred_bedrooms: 2
    preferred_bathrooms: 2
"""
        )
        console.print(f"✓ Created {config_file}", style="green")

    # Create communities config
    communities_file = config_dir / "communities.yaml"
    if not communities_file.exists():
        communities_file.write_text(
            """\
# Communities to track for availability

communities:
  # Highest Priority: Irvine Company - Santa Clara Square
  - name: "Santa Clara Square"
    management: irvine
    url: "https://www.irvinecompanyapartments.com/locations/northern-california/santa-clara/santa-clara-square/availability.html"
    priority: 1
    enabled: true

  # Prometheus Apartments - Mountain View
  - name: "100 Moffett"
    management: prometheus
    url: "https://prometheusapartments.com/ca/mountain-view-apartments/100-moffett"
    priority: 2
    enabled: false  # Enable when prometheus scraper is ready

  - name: "The Dean"
    management: prometheus
    url: "https://prometheusapartments.com/ca/mountain-view-apartments/the-dean"
    priority: 3
    enabled: false

  - name: "The Tillery"
    management: prometheus
    url: "https://prometheusapartments.com/ca/mountain-view-apartments/the-tillery"
    priority: 4
    enabled: false

  - name: "The Hadley"
    management: prometheus
    url: "https://prometheusapartments.com/ca/mountain-view-apartments/the-hadley"
    priority: 5
    enabled: false

  - name: "Montrose"
    management: prometheus
    url: "https://prometheusapartments.com/ca/mountain-view-apartments/montrose"
    priority: 6
    enabled: false

  - name: "Hearth"
    management: prometheus
    url: "https://prometheusapartments.com/ca/santa-clara-apartments/hearth"
    priority: 7
    enabled: false
"""
        )
        console.print(f"✓ Created {communities_file}", style="green")

    # Create .env.example
    env_example = Path(".env.example")
    if not env_example.exists():
        env_example.write_text(
            """\
# Environment variables for Apartment Tracker
# Copy this to .env and fill in your values

# Discord webhook for notifications
# APARTMENT_TRACKER_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Email credentials (for Gmail, use an App Password)
# APARTMENT_TRACKER_EMAIL_USERNAME=your-email@gmail.com
# APARTMENT_TRACKER_EMAIL_PASSWORD=your-app-password

# OR SendGrid API key
# APARTMENT_TRACKER_SENDGRID_API_KEY=SG.xxx

# LLM API keys for direction detection
# APARTMENT_TRACKER_GEMINI_API_KEY=your-gemini-api-key
# APARTMENT_TRACKER_OPENAI_API_KEY=sk-xxx

# Optional: PostgreSQL connection string
# APARTMENT_TRACKER_DATABASE_URL=postgresql://user:pass@host:5432/dbname
"""
        )
        console.print(f"✓ Created {env_example}", style="green")

    # Create data directories
    Path("data").mkdir(exist_ok=True)
    Path("data/floor_plans").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    console.print("\n✓ Initialization complete!", style="bold green")
    console.print("\nNext steps:")
    console.print("1. Edit config/config.yaml with your settings")
    console.print("2. Copy .env.example to .env and add your API keys")
    console.print("3. Run: apartment-tracker run")


@app.command()
def run(
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        "-c",
        help="Configuration directory",
    ),
    once: bool = typer.Option(
        True,
        "--once/--loop",
        help="Run once and exit, or loop continuously",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--visible",
        help="Run browser in headless mode",
    ),
) -> None:
    """Run the apartment tracker to scrape availability."""
    config = load_config(config_dir)
    setup_logging(config.logging.level, config.logging.file)

    logger = logging.getLogger("apartment_tracker")
    logger.info("Starting apartment tracker")

    # Initialize database
    db_url = get_database_url(config)
    engine = get_engine(db_url)
    create_tables(engine)
    logger.info(f"Database initialized: {db_url}")

    # Get enabled communities sorted by priority
    enabled_communities = [c for c in config.communities if c.enabled]
    enabled_communities.sort(key=lambda c: c.priority)

    if not enabled_communities:
        console.print("⚠ No communities enabled. Check config/communities.yaml", style="yellow")
        return

    console.print(f"Tracking {len(enabled_communities)} communities", style="bold")

    # Run the scraping
    asyncio.run(
        scrape_all(
            config=config,
            engine=engine,
            communities=enabled_communities,
            headless=headless,
        )
    )


async def scrape_all(config: Config, engine, communities: list, headless: bool) -> None:
    """Scrape all enabled communities."""
    logger = logging.getLogger("apartment_tracker")

    for community in communities:
        try:
            scraper_class = get_scraper(community.management)

            async with scraper_class(
                headless=headless,
                request_delay_seconds=config.scraping.request_delay_seconds,
                screenshot_on_error=config.scraping.screenshot_on_error,
            ) as scraper:
                logger.info(f"Scraping {community.name} ({community.management})")
                listings = await scraper.scrape_availability(community.url)

                if listings:
                    save_listings(engine, listings, community)
                    display_listings(listings)
                else:
                    logger.warning(f"No listings found for {community.name}")

        except ValueError as e:
            logger.error(f"Scraper error for {community.name}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error scraping {community.name}: {e}")

        # Delay between communities
        if community != communities[-1]:
            await asyncio.sleep(config.scraping.request_delay_seconds)


def save_listings(engine, listings: list[ListingData], community) -> None:
    """Save scraped listings to the database."""
    logger = logging.getLogger("apartment_tracker")

    with get_session(engine) as session:
        for listing_data in listings:
            # Check if listing already exists
            existing = session.get(Listing, listing_data.id)

            if existing:
                # Update last_seen
                existing.last_seen = listing_data.available_date or existing.last_seen
                existing.is_active = True

                # Check for price change
                latest_price = (
                    session.query(PriceHistory)
                    .filter(PriceHistory.listing_id == listing_data.id)
                    .order_by(PriceHistory.recorded_at.desc())
                    .first()
                )

                if not latest_price or latest_price.price != listing_data.price:
                    # Record new price
                    price_entry = PriceHistory(
                        listing_id=listing_data.id,
                        price=listing_data.price,
                        available_date=listing_data.available_date,
                    )
                    session.add(price_entry)
                    logger.info(f"Price update: {listing_data.unit_number} -> ${listing_data.price}")

            else:
                # Create new listing
                new_listing = Listing(
                    id=listing_data.id,
                    community_id=1,  # TODO: Get or create community
                    unit_number=listing_data.unit_number,
                    floor=listing_data.floor,
                    floor_plan_name=listing_data.floor_plan_name,
                    floor_plan_image_path=None,  # TODO: Download and save
                    bedrooms=listing_data.bedrooms,
                    bathrooms=listing_data.bathrooms,
                    sqft=listing_data.sqft,
                    facing_direction=listing_data.facing_direction,
                    view_type=listing_data.view_type,
                    listing_url=listing_data.listing_url,
                )
                session.add(new_listing)

                # Record initial price
                price_entry = PriceHistory(
                    listing_id=listing_data.id,
                    price=listing_data.price,
                    available_date=listing_data.available_date,
                )
                session.add(price_entry)

                logger.info(f"New listing: {listing_data.unit_number} - ${listing_data.price}")

        session.commit()


def display_listings(listings: list[ListingData]) -> None:
    """Display listings in a nice table."""
    table = Table(title=f"Found {len(listings)} Listings")

    table.add_column("Unit", style="cyan")
    table.add_column("Plan", style="dim")
    table.add_column("Beds", justify="center")
    table.add_column("Baths", justify="center")
    table.add_column("Sq Ft", justify="right")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Term", justify="center")
    table.add_column("Floor", justify="center")
    table.add_column("Available", style="yellow")

    for listing in listings:
        # Format bedrooms (0 = Studio, 0.5 = Loft/Studio, 1.5 = 1+Den, etc.)
        if listing.bedrooms == 0:
            beds_str = "Studio"
        elif listing.bedrooms == int(listing.bedrooms):
            beds_str = str(int(listing.bedrooms))
        else:
            beds_str = f"{listing.bedrooms:.1f}"

        # Format bathrooms (1.0 = 1, 1.5 = 1.5)
        if listing.bathrooms == int(listing.bathrooms):
            baths_str = str(int(listing.bathrooms))
        else:
            baths_str = f"{listing.bathrooms:.1f}"

        # Format available date as MM/DD/YY
        date_str = listing.available_date.strftime("%m/%d/%y") if listing.available_date else "-"

        # Format lease term
        term_str = f"{listing.lease_term_months}mo" if listing.lease_term_months else "-"

        table.add_row(
            listing.unit_number,
            listing.floor_plan_name or "-",
            beds_str,
            baths_str,
            f"{listing.sqft:,}" if listing.sqft else "-",
            f"${listing.price:,}",
            term_str,
            str(listing.floor) if listing.floor else "-",
            date_str,
        )

    console.print(table)


@app.command()
def list_communities(
    config_dir: Path = typer.Option(
        Path("config"),
        "--config-dir",
        "-c",
        help="Configuration directory",
    ),
) -> None:
    """List configured communities."""
    config = load_config(config_dir)

    table = Table(title="Configured Communities")
    table.add_column("Priority", justify="center", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Management")
    table.add_column("Enabled", justify="center")
    table.add_column("URL")

    for community in sorted(config.communities, key=lambda c: c.priority):
        table.add_row(
            str(community.priority),
            community.name,
            community.management,
            "✓" if community.enabled else "✗",
            community.url[:50] + "..." if len(community.url) > 50 else community.url,
        )

    console.print(table)


@app.command()
def test_scraper(
    url: str = typer.Argument(..., help="URL to scrape"),
    management: str = typer.Option(
        "irvine",
        "--management",
        "-m",
        help="Management company (irvine, prometheus, etc.)",
    ),
    headless: bool = typer.Option(
        False,
        "--headless/--visible",
        help="Run browser in headless mode",
    ),
) -> None:
    """Test a scraper against a specific URL."""
    setup_logging("DEBUG")

    async def _test():
        scraper_class = get_scraper(management)
        async with scraper_class(headless=headless) as scraper:
            console.print(f"Testing {management} scraper on: {url}", style="bold")
            listings = await scraper.scrape_availability(url)
            if listings:
                display_listings(listings)
            else:
                console.print("No listings found", style="yellow")

    asyncio.run(_test())


if __name__ == "__main__":
    app()
