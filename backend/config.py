"""
Configuration management for AI Trading Bot v2
"""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # API Configuration
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # NOTE: Robinhood credentials are now entered via web login screen
    # These environment variables are no longer used

    # AWS Configuration
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_ENABLED: bool = True

    # Database Configuration
    DATABASE_PATH: str = "data/trading.db"

    # Cache TTLs (in seconds)
    CACHE_TTL_MARKET_DATA: int = 300  # 5 minutes
    CACHE_TTL_NEWS: int = 600  # 10 minutes
    CACHE_TTL_QUOTE: int = 60  # 1 minute for real-time quotes

    # Trading Configuration
    # NOTE: DEFAULT_TAKE_PROFIT, DEFAULT_STOP_LOSS, and MAX_POSITION_SIZE
    # are now configured via the Settings page in the web interface
    DEFAULT_TAKE_PROFIT: float = 0.20  # 20% (default only, overridden by settings page)
    DEFAULT_STOP_LOSS: float = 0.20  # 20% (default only, overridden by settings page)
    MAX_POSITION_SIZE: float = 1000.0  # (default only, overridden by settings page)
    RISK_PER_TRADE: float = 0.02  # 2% of account

    # Monitoring Configuration
    POSITION_CHECK_INTERVAL: int = 30  # seconds

    # Market Schedule Configuration
    SKIP_MARKET_SCHEDULE_CHECK: bool = False  # Set to True for testing outside market hours
    BLOCK_FIRST_HOUR_TRADING: bool = True  # Block trades during first hour (9:30-10:30 AM ET) due to high volatility

    # AI Configuration
    AI_MODEL_ID: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    AI_MAX_TOKENS: int = 2000  # Increased for entry/exit point rationale
    BATCH_ANALYSIS_SIZE: int = 10  # Analyze up to 10 tickers in one AI call

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
