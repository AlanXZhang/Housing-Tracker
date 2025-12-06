# Apartment Availability Tracker

Monitor apartment availability across multiple property management companies and get notified when listings match your criteria.

## Features

- 🏠 Scrape availability from Irvine Company and Prometheus apartments
- 🔍 Filter by floor, price, size, bedrooms, and more
- 🧭 LLM-powered direction detection from floor plans
- 📱 Discord and email notifications
- 📊 Price history tracking
- 🗄️ SQLite database with optional PostgreSQL

## Quick Start

```bash
# Install dependencies
pip install -e ".[all]"

# Install Playwright browsers
playwright install chromium

# Copy and edit config
cp config/config.example.yaml config/config.yaml

# Run the tracker
apartment-tracker run
```

## Configuration

Edit `config/config.yaml` to set up:
- Target communities to monitor
- Notification settings (Discord webhook, email)
- Filter criteria

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/

# Type check
mypy src/
```

## License

MIT
