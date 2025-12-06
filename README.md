# Apartment Availability Tracker

Monitor apartment availability across multiple property management companies and get notified when listings match your criteria.

## Features

- 🏠 **Web Scraping**: Scrape availability from Irvine Company apartments (Prometheus coming soon)
- 🔍 **Smart Filtering**: Filter by floor, price, size, bedrooms, bathrooms, and more
- 🧭 **LLM Direction Detection**: Analyze floor plans to detect facing direction (South, Southwest, etc.)
- 📱 **Notifications**: Discord webhooks and email alerts for matching listings
- 📊 **Price Tracking**: Historical price tracking per unit
- 🗄️ **Database**: SQLite by default, PostgreSQL optional

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/house-tracker.git
cd house-tracker

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[all]"

# Install Playwright browsers
playwright install chromium
```

### 2. Initialize Configuration

```bash
# Create default config files
apartment-tracker init
```

This creates:
- `config/config.yaml` - Main configuration
- `config/communities.yaml` - Communities to track
- `.env.example` - Environment variables template

### 3. Configure Settings

Edit `config/config.yaml`:

```yaml
filters:
  required:
    min_floor: 2          # Minimum floor (e.g., avoid ground floor)
    min_sqft: 680         # Minimum square footage
    min_bedrooms: 1       # Minimum bedrooms (0 = include studios)
    max_price: 4699       # Maximum monthly rent

  preferred:
    preferred_directions:
      - S                 # South-facing (best light)
      - SW                # Southwest
```

### 4. (Optional) Set Up Notifications

Copy `.env.example` to `.env` and add your credentials:

```bash
# Discord webhook for notifications
APARTMENT_TRACKER_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Email (Gmail with App Password)
APARTMENT_TRACKER_EMAIL_USERNAME=your-email@gmail.com
APARTMENT_TRACKER_EMAIL_PASSWORD=your-app-password

# LLM API key for direction detection
APARTMENT_TRACKER_GEMINI_API_KEY=your-gemini-api-key
```

### 5. Run the Tracker

```bash
# Test a specific URL
apartment-tracker test-scraper "https://www.irvinecompanyapartments.com/locations/northern-california/santa-clara/santa-clara-square/availability.html" --management irvine

# Run the full tracker
apartment-tracker run

# Run in visible browser mode (for debugging)
apartment-tracker test-scraper "URL" --visible
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `apartment-tracker init` | Initialize config files |
| `apartment-tracker run` | Run the tracker (scrape all enabled communities) |
| `apartment-tracker list-communities` | Show configured communities |
| `apartment-tracker test-scraper URL` | Test scraping a specific URL |
| `apartment-tracker version` | Show version |

## Data Extracted

The scraper extracts the following for each available unit:

| Field | Type | Description |
|-------|------|-------------|
| `unit_number` | string | Building-Unit format (e.g., "04-256") |
| `floor_plan_name` | string | Plan identifier (e.g., "PLAN 30", "PLAN 30 Alt") |
| `bedrooms` | float | 0=Studio, 0.5=Loft/Studio, 1.5=1+Den, 2.5=Loft/2Bed |
| `bathrooms` | float | 1.0=1 bath, 1.5=1 full + 1 half |
| `sqft` | int | Minimum from range (e.g., 1,067-1,123 → 1067) |
| `price` | int | Monthly rent in dollars |
| `lease_term_months` | int | Lease length (e.g., 12, 13, 14) |
| `floor` | int | Floor number |
| `available_date` | datetime | Move-in date (MM/DD/YY format) |

## Project Structure

```
house-tracker/
├── src/apartment_tracker/
│   ├── scrapers/          # Web scrapers (Irvine, Prometheus)
│   ├── models/            # Database models and Pydantic schemas
│   ├── analysis/          # LLM direction detection
│   ├── filters/           # Criteria filtering engine
│   ├── notifications/     # Discord and email notifiers
│   ├── config.py          # Configuration management
│   └── main.py            # CLI entry point
├── config/                # Configuration files (gitignored)
├── data/                  # Database and floor plan images (gitignored)
└── tests/                 # Test suite
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type check
mypy src/
```

## License

MIT
