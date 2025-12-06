"""Configuration management for Apartment Tracker."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseModel):
    """Database configuration."""

    type: str = "sqlite"
    path: str = "./data/apartment_tracker.db"
    url: str | None = None  # For PostgreSQL


class ScrapingConfig(BaseModel):
    """Web scraping configuration."""

    interval_minutes: int = 30
    request_delay_seconds: int = 45
    max_retries: int = 3
    headless: bool = True
    screenshot_on_error: bool = True


class DiscordConfig(BaseModel):
    """Discord notification configuration."""

    enabled: bool = False
    webhook_url: str | None = None


class EmailConfig(BaseModel):
    """Email notification configuration."""

    enabled: bool = False
    provider: str = "smtp"  # smtp or sendgrid
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str | None = None
    password: str | None = None
    sendgrid_api_key: str | None = None
    recipients: list[str] = Field(default_factory=list)
    mode: str = "immediate"  # immediate or digest
    digest_interval_hours: int = 6


class NotificationsConfig(BaseModel):
    """Notification system configuration."""

    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)


class LLMConfig(BaseModel):
    """LLM configuration for direction detection."""

    provider: str = "gemini"  # gemini, openai, or anthropic
    api_key: str | None = None
    model: str = "gemini-1.5-flash"


class LoggingConfig(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    file: str = "./logs/scraper.log"
    max_size_mb: int = 10
    backup_count: int = 5


class Community(BaseModel):
    """A single apartment community to track."""

    name: str
    management: str  # irvine, prometheus, essex, greystar
    url: str
    enabled: bool = True
    priority: int = 10  # Lower number = higher priority


class RequiredFilters(BaseModel):
    """Required filters - listings must pass all of these."""

    min_floor: int = 2
    min_sqft: int = 680
    min_bedrooms: int = 1
    min_bathrooms: int = 1
    max_price: int = 4699


class PreferredFilters(BaseModel):
    """Preferred filters - used for scoring."""

    preferred_directions: list[str] = Field(default_factory=lambda: ["S", "SW"])
    min_sqft_preferred: int = 850
    preferred_bedrooms: int = 2
    preferred_bathrooms: int = 2


class FiltersConfig(BaseModel):
    """Filter configuration."""

    required: RequiredFilters = Field(default_factory=RequiredFilters)
    preferred: PreferredFilters = Field(default_factory=PreferredFilters)


class Config(BaseModel):
    """Main application configuration."""

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    scraping: ScrapingConfig = Field(default_factory=ScrapingConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    communities: list[Community] = Field(default_factory=list)
    filters: FiltersConfig = Field(default_factory=FiltersConfig)


class Settings(BaseSettings):
    """Environment-based settings that override config file values."""

    model_config = SettingsConfigDict(
        env_prefix="APARTMENT_TRACKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str | None = None

    # Discord
    discord_webhook_url: str | None = None

    # Email
    email_username: str | None = None
    email_password: str | None = None
    sendgrid_api_key: str | None = None

    # LLM
    gemini_api_key: str | None = None
    openai_api_key: str | None = None


def load_yaml_config(config_path: Path) -> dict[str, Any]:
    """Load configuration from YAML file."""
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        return yaml.safe_load(f) or {}


def load_config(
    config_dir: Path | None = None,
    env_settings: Settings | None = None,
) -> Config:
    """Load and merge configuration from files and environment.

    Priority (highest to lowest):
    1. Environment variables
    2. config.yaml
    3. Default values
    """
    if config_dir is None:
        config_dir = Path("config")

    # Load YAML configs
    main_config = load_yaml_config(config_dir / "config.yaml")
    communities_config = load_yaml_config(config_dir / "communities.yaml")

    # Merge communities into main config
    if "communities" in communities_config:
        main_config["communities"] = communities_config["communities"]

    # Create config from YAML
    config = Config(**main_config) if main_config else Config()

    # Override with environment variables
    if env_settings is None:
        env_settings = Settings()

    if env_settings.database_url:
        config.database.url = env_settings.database_url
        config.database.type = "postgresql"

    if env_settings.discord_webhook_url:
        config.notifications.discord.webhook_url = env_settings.discord_webhook_url
        config.notifications.discord.enabled = True

    if env_settings.email_username:
        config.notifications.email.username = env_settings.email_username
    if env_settings.email_password:
        config.notifications.email.password = env_settings.email_password
    if env_settings.sendgrid_api_key:
        config.notifications.email.sendgrid_api_key = env_settings.sendgrid_api_key

    if env_settings.gemini_api_key:
        config.llm.api_key = env_settings.gemini_api_key
        config.llm.provider = "gemini"
    elif env_settings.openai_api_key:
        config.llm.api_key = env_settings.openai_api_key
        config.llm.provider = "openai"

    return config
