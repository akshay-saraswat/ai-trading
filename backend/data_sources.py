"""
Intelligent Data Source Fallback System
Automatically switches between yfinance, AlphaVantage, and Finnhub when rate limits are hit
"""
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, List, Dict, Any
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class DataSourceType(Enum):
    """Enum for different data source types"""
    YFINANCE = "yfinance"
    ALPHA_VANTAGE = "alphavantage"
    FINNHUB = "finnhub"


class RateLimitError(Exception):
    """Custom exception for rate limit errors"""
    pass


@dataclass
class CircuitBreakerState:
    """Tracks circuit breaker state for a data source"""
    failure_count: int = 0
    last_failure_time: Optional[float] = None
    is_open: bool = False
    success_count: int = 0

    # Circuit breaker thresholds
    FAILURE_THRESHOLD: int = 3  # Open circuit after 3 failures
    SUCCESS_THRESHOLD: int = 2  # Close circuit after 2 successes
    TIMEOUT_SECONDS: int = 300  # 5 minutes cooldown

    def record_failure(self):
        """Record a failure and potentially open the circuit"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.success_count = 0

        if self.failure_count >= self.FAILURE_THRESHOLD:
            self.is_open = True
            logger.warning(f"Circuit breaker OPENED after {self.failure_count} failures")

    def record_success(self):
        """Record a success and potentially close the circuit"""
        self.success_count += 1
        self.failure_count = 0

        if self.is_open and self.success_count >= self.SUCCESS_THRESHOLD:
            self.is_open = False
            logger.info("Circuit breaker CLOSED after successful recoveries")

    def can_attempt(self) -> bool:
        """Check if we can attempt a call (circuit not open or timeout expired)"""
        if not self.is_open:
            return True

        # Check if timeout has expired (half-open state)
        if self.last_failure_time:
            time_since_failure = time.time() - self.last_failure_time
            if time_since_failure >= self.TIMEOUT_SECONDS:
                logger.info("Circuit breaker entering HALF-OPEN state (timeout expired)")
                self.is_open = False
                self.failure_count = 0
                return True

        return False


class DataSource(ABC):
    """Abstract base class for data sources"""

    def __init__(self, name: str):
        self.name = name
        self.circuit_breaker = CircuitBreakerState()
        self._session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def is_available(self) -> bool:
        """Check if this data source is available"""
        return self.circuit_breaker.can_attempt()

    def _handle_success(self):
        """Record successful API call"""
        self.circuit_breaker.record_success()

    def _handle_failure(self, error: Exception):
        """Record failed API call"""
        logger.error(f"{self.name} failure: {error}")
        self.circuit_breaker.record_failure()

    @abstractmethod
    async def get_historical_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV data"""
        pass

    @abstractmethod
    async def get_quote(self, ticker: str) -> Optional[float]:
        """Fetch real-time quote"""
        pass

    @abstractmethod
    async def get_news(self, ticker: str) -> List[Dict]:
        """Fetch news articles"""
        pass


class YFinanceDataSource(DataSource):
    """YFinance data source (primary)"""

    def __init__(self):
        super().__init__("YFinance")
        import yfinance as yf
        self.yf = yf

    def _is_rate_limit_error(self, error: Exception) -> bool:
        """Check if error is due to rate limiting"""
        error_msg = str(error).lower()
        rate_limit_indicators = [
            'rate limit', 'too many requests', '429', 'quota',
            'throttle', 'temporarily unavailable'
        ]
        return any(indicator in error_msg for indicator in rate_limit_indicators)

    async def get_historical_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch historical data from yfinance"""
        if not self.is_available():
            raise RateLimitError(f"{self.name} circuit breaker is OPEN")

        try:
            df = self.yf.download(ticker, period="1y", progress=False)

            if df is None or df.empty:
                raise ValueError(f"No data returned for {ticker}")

            # Flatten MultiIndex columns if needed
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Rename Adj Close
            if 'Adj Close' in df.columns:
                df = df.rename(columns={'Adj Close': 'Adj_Close'})

            self._handle_success()
            return df

        except Exception as e:
            if self._is_rate_limit_error(e):
                self._handle_failure(RateLimitError(f"Rate limit hit: {e}"))
                raise RateLimitError(f"YFinance rate limit: {e}")
            self._handle_failure(e)
            raise

    async def get_quote(self, ticker: str) -> Optional[float]:
        """Fetch real-time quote from yfinance"""
        if not self.is_available():
            raise RateLimitError(f"{self.name} circuit breaker is OPEN")

        try:
            stock = self.yf.Ticker(ticker)
            info = stock.info
            price = info.get('currentPrice') or info.get('regularMarketPrice')

            if not price:
                raise ValueError(f"No price data for {ticker}")

            self._handle_success()
            return float(price)

        except Exception as e:
            if self._is_rate_limit_error(e):
                self._handle_failure(RateLimitError(f"Rate limit hit: {e}"))
                raise RateLimitError(f"YFinance rate limit: {e}")
            self._handle_failure(e)
            raise

    async def get_news(self, ticker: str) -> List[Dict]:
        """Fetch news from yfinance"""
        if not self.is_available():
            raise RateLimitError(f"{self.name} circuit breaker is OPEN")

        try:
            stock = self.yf.Ticker(ticker)
            raw_news = stock.news

            if not raw_news:
                return []

            news_list = []
            for n in raw_news[:15]:
                if isinstance(n, dict):
                    news_list.append({
                        'title': n.get('title', ''),
                        'publisher': n.get('publisher', 'Unknown'),
                        'link': n.get('link', ''),
                        'published': n.get('providerPublishTime', 0),
                        'summary': n.get('summary', '')
                    })

            self._handle_success()
            return news_list

        except Exception as e:
            if self._is_rate_limit_error(e):
                self._handle_failure(RateLimitError(f"Rate limit hit: {e}"))
                raise RateLimitError(f"YFinance rate limit: {e}")
            self._handle_failure(e)
            raise


class AlphaVantageDataSource(DataSource):
    """AlphaVantage data source (fallback for historical data & quotes)"""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str):
        super().__init__("AlphaVantage")
        self.api_key = api_key

    def _is_rate_limit_error(self, response_data: Dict) -> bool:
        """Check if API response indicates rate limiting"""
        if isinstance(response_data, dict):
            note = response_data.get('Note', '').lower()
            info = response_data.get('Information', '').lower()
            return 'api call frequency' in note or 'premium' in note or 'rate' in info
        return False

    async def get_historical_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch daily historical data from AlphaVantage"""
        if not self.is_available():
            raise RateLimitError(f"{self.name} circuit breaker is OPEN")

        try:
            params = {
                'function': 'TIME_SERIES_DAILY',
                'symbol': ticker,
                'outputsize': 'full',  # Get full data (20+ years)
                'apikey': self.api_key
            }

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._session.get(self.BASE_URL, params=params, timeout=10)
            )
            response.raise_for_status()
            data = response.json()

            # Check for rate limiting
            if self._is_rate_limit_error(data):
                raise RateLimitError("AlphaVantage rate limit exceeded")

            # Parse time series data
            time_series = data.get('Time Series (Daily)', {})
            if not time_series:
                raise ValueError(f"No data available for {ticker}")

            # Convert to DataFrame
            df = pd.DataFrame.from_dict(time_series, orient='index')
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()

            # Rename columns to match yfinance format
            df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            df = df.astype(float)

            # Get only last 1 year to match yfinance behavior
            one_year_ago = datetime.now() - timedelta(days=365)
            df = df[df.index >= one_year_ago]

            # Add Adj_Close (same as Close for AlphaVantage)
            df['Adj_Close'] = df['Close']

            self._handle_success()
            logger.info(f"AlphaVantage: Successfully fetched {len(df)} days for {ticker}")
            return df

        except RateLimitError:
            self._handle_failure(RateLimitError("AlphaVantage rate limit"))
            raise
        except Exception as e:
            self._handle_failure(e)
            raise

    async def get_quote(self, ticker: str) -> Optional[float]:
        """Fetch real-time quote from AlphaVantage"""
        if not self.is_available():
            raise RateLimitError(f"{self.name} circuit breaker is OPEN")

        try:
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': ticker,
                'apikey': self.api_key
            }

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._session.get(self.BASE_URL, params=params, timeout=10)
            )
            response.raise_for_status()
            data = response.json()

            # Check for rate limiting
            if self._is_rate_limit_error(data):
                raise RateLimitError("AlphaVantage rate limit exceeded")

            quote = data.get('Global Quote', {})
            price_str = quote.get('05. price')

            if not price_str:
                raise ValueError(f"No quote data for {ticker}")

            price = float(price_str)
            self._handle_success()
            logger.info(f"AlphaVantage: Quote for {ticker} = ${price}")
            return price

        except RateLimitError:
            self._handle_failure(RateLimitError("AlphaVantage rate limit"))
            raise
        except Exception as e:
            self._handle_failure(e)
            raise

    async def get_news(self, ticker: str) -> List[Dict]:
        """AlphaVantage doesn't provide news - return empty list"""
        return []


class FinnhubDataSource(DataSource):
    """Finnhub data source (fallback for news only)"""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, api_key: str):
        super().__init__("Finnhub")
        self.api_key = api_key

    def _is_rate_limit_error(self, status_code: int) -> bool:
        """Check if status code indicates rate limiting"""
        return status_code == 429

    async def get_historical_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Finnhub is not used for historical data"""
        raise NotImplementedError("Finnhub does not support historical data")

    async def get_quote(self, ticker: str) -> Optional[float]:
        """Finnhub is not used for quotes in this implementation"""
        raise NotImplementedError("Finnhub quote support not implemented")

    async def get_news(self, ticker: str) -> List[Dict]:
        """Fetch company news from Finnhub"""
        if not self.is_available():
            raise RateLimitError(f"{self.name} circuit breaker is OPEN")

        try:
            # Get news from last 7 days
            to_date = datetime.now().strftime('%Y-%m-%d')
            from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

            params = {
                'symbol': ticker,
                'from': from_date,
                'to': to_date,
                'token': self.api_key
            }

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._session.get(
                    f"{self.BASE_URL}/company-news",
                    params=params,
                    timeout=10
                )
            )

            if self._is_rate_limit_error(response.status_code):
                raise RateLimitError("Finnhub rate limit exceeded")

            response.raise_for_status()
            data = response.json()

            if not data or not isinstance(data, list):
                return []

            news_list = []
            for article in data[:15]:
                news_list.append({
                    'title': article.get('headline', ''),
                    'publisher': article.get('source', 'Unknown'),
                    'link': article.get('url', ''),
                    'published': article.get('datetime', 0),
                    'summary': article.get('summary', '')
                })

            self._handle_success()
            logger.info(f"Finnhub: Fetched {len(news_list)} articles for {ticker}")
            return news_list

        except RateLimitError:
            self._handle_failure(RateLimitError("Finnhub rate limit"))
            raise
        except Exception as e:
            self._handle_failure(e)
            raise


class DataSourceOrchestrator:
    """
    Intelligent orchestrator that manages multiple data sources with automatic fallback.
    Uses circuit breaker pattern to handle rate limits gracefully.
    """

    def __init__(
        self,
        alpha_vantage_key: Optional[str] = None,
        finnhub_key: Optional[str] = None
    ):
        """Initialize orchestrator with all available data sources"""
        self.sources: Dict[str, DataSource] = {}

        # Primary source: YFinance (always available)
        self.sources['yfinance'] = YFinanceDataSource()

        # Fallback sources
        if alpha_vantage_key:
            self.sources['alphavantage'] = AlphaVantageDataSource(alpha_vantage_key)
            logger.info("AlphaVantage data source enabled")

        if finnhub_key:
            self.sources['finnhub'] = FinnhubDataSource(finnhub_key)
            logger.info("Finnhub data source enabled")

        # Define priority order for each data type
        self.historical_data_priority = ['yfinance', 'alphavantage']
        self.quote_priority = ['yfinance', 'alphavantage']
        self.news_priority = ['yfinance', 'finnhub']

    async def get_historical_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """
        Fetch historical data with intelligent fallback.
        Tries sources in priority order until one succeeds.
        """
        last_error = None

        for source_name in self.historical_data_priority:
            source = self.sources.get(source_name)
            if not source:
                continue

            if not source.is_available():
                logger.warning(f"{source_name} unavailable (circuit breaker OPEN), trying next source")
                continue

            try:
                logger.info(f"Attempting historical data fetch for {ticker} from {source_name}")
                data = await source.get_historical_data(ticker)
                if data is not None and not data.empty:
                    logger.info(f"✓ Successfully fetched historical data from {source_name}")
                    return data
            except RateLimitError as e:
                logger.warning(f"{source_name} rate limit hit: {e}")
                last_error = e
                continue
            except Exception as e:
                logger.error(f"{source_name} error: {e}")
                last_error = e
                continue

        logger.error(f"All data sources failed for {ticker}. Last error: {last_error}")
        return None

    async def get_quote(self, ticker: str) -> Optional[float]:
        """
        Fetch real-time quote with intelligent fallback.
        Tries sources in priority order until one succeeds.
        """
        last_error = None

        for source_name in self.quote_priority:
            source = self.sources.get(source_name)
            if not source:
                continue

            if not source.is_available():
                logger.warning(f"{source_name} unavailable (circuit breaker OPEN), trying next source")
                continue

            try:
                logger.info(f"Attempting quote fetch for {ticker} from {source_name}")
                quote = await source.get_quote(ticker)
                if quote is not None:
                    logger.info(f"✓ Successfully fetched quote from {source_name}")
                    return quote
            except RateLimitError as e:
                logger.warning(f"{source_name} rate limit hit: {e}")
                last_error = e
                continue
            except Exception as e:
                logger.error(f"{source_name} error: {e}")
                last_error = e
                continue

        logger.error(f"All quote sources failed for {ticker}. Last error: {last_error}")
        return None

    async def get_news(self, ticker: str) -> List[Dict]:
        """
        Fetch news with intelligent fallback.
        Tries sources in priority order until one succeeds.
        """
        last_error = None

        for source_name in self.news_priority:
            source = self.sources.get(source_name)
            if not source:
                continue

            if not source.is_available():
                logger.warning(f"{source_name} unavailable (circuit breaker OPEN), trying next source")
                continue

            try:
                logger.info(f"Attempting news fetch for {ticker} from {source_name}")
                news = await source.get_news(ticker)
                if news:
                    logger.info(f"✓ Successfully fetched {len(news)} articles from {source_name}")
                    return news
            except RateLimitError as e:
                logger.warning(f"{source_name} rate limit hit: {e}")
                last_error = e
                continue
            except Exception as e:
                logger.error(f"{source_name} error: {e}")
                last_error = e
                continue

        logger.warning(f"All news sources failed for {ticker}. Last error: {last_error}")
        return []

    def get_status(self) -> Dict[str, Any]:
        """Get status of all data sources (for monitoring/debugging)"""
        status = {}
        for name, source in self.sources.items():
            cb = source.circuit_breaker
            status[name] = {
                'available': source.is_available(),
                'circuit_open': cb.is_open,
                'failure_count': cb.failure_count,
                'success_count': cb.success_count,
                'last_failure': datetime.fromtimestamp(cb.last_failure_time).isoformat()
                    if cb.last_failure_time else None
            }
        return status
