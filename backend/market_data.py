"""
Optimized Market Data Layer with Redis Caching
Supports stocks and index options (SPX, NDX, RUT, etc.)
Uses only yfinance - no investpy dependency
"""
import pandas as pd
import ta
import yfinance as yf
import asyncio
from typing import Optional, List, Dict
import logging
from datetime import datetime, timedelta

from .cache import cache
from .config import settings

logger = logging.getLogger(__name__)

# Suppress yfinance debug/error logs to reduce noise
logging.getLogger('yfinance').setLevel(logging.CRITICAL)


class MarketData:
    """Market data fetcher with intelligent caching"""

    # Index ticker mappings (yfinance uses ^prefix for indices)
    INDEX_MAPPINGS = {
        'SPX': '^SPX',   # S&P 500
        'NDX': '^NDX',   # NASDAQ 100
        'RUT': '^RUT',   # Russell 2000
        'VIX': '^VIX',   # Volatility Index
        'DJI': '^DJI',   # Dow Jones Industrial
    }

    def __init__(self):
        pass

    def _normalize_ticker(self, ticker: str) -> str:
        """Normalize ticker (handle index symbols)"""
        ticker_upper = ticker.upper()
        return self.INDEX_MAPPINGS.get(ticker_upper, ticker_upper)

    def _is_valid_ticker(self, ticker: str) -> bool:
        """
        Validate ticker symbol to filter out problematic tickers.
        Returns True if ticker is likely valid.
        """
        if not ticker or len(ticker) > 6:
            return False

        # Skip common problematic patterns (but allow - for some valid tickers)
        invalid_patterns = ['^', '=', '/', ' ']
        if any(pattern in ticker for pattern in invalid_patterns):
            return False

        # Must be mostly alphanumeric (allow one dash or dot)
        cleaned = ticker.replace('-', '').replace('.', '')
        if not cleaned.isalnum():
            return False

        return True

    async def get_stock_data(self, ticker: str, use_cache: bool = True) -> Optional[pd.DataFrame]:
        """
        Fetch historical stock data with technical indicators.
        Uses Redis cache (5 min TTL) to reduce Yahoo Finance calls.

        Args:
            ticker: Stock/Index symbol
            use_cache: Whether to use cache

        Returns:
            DataFrame with OHLCV + technical indicators or None
        """
        normalized_ticker = self._normalize_ticker(ticker)
        cache_key = f"market_data:{normalized_ticker}"

        # Try cache first
        if use_cache:
            cached = await cache.get(cache_key)
            if cached:
                logger.debug(f"Cache HIT: {normalized_ticker}")
                # Reconstruct DataFrame
                df = pd.DataFrame(cached['data'])
                df.index = pd.to_datetime(cached['index'])
                return df

        logger.debug(f"Cache MISS: {normalized_ticker} - fetching from Yahoo Finance")

        # Fetch from yfinance using download method (more reliable than Ticker.history)
        try:
            # Use yf.download() which is more stable
            df = yf.download(
                normalized_ticker,
                period="1y",
                progress=False
            )

            if df is None or df.empty:
                logger.warning(f"No data found for {normalized_ticker}")
                return None

            # yf.download() returns MultiIndex columns for single ticker, flatten them
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Rename 'Adj Close' to match expected format
            if 'Adj Close' in df.columns:
                df = df.rename(columns={'Adj Close': 'Adj_Close'})

            # Add technical indicators
            df = self._add_technical_indicators(df)

            # Cache for 5 minutes
            if use_cache:
                cache_data = {
                    'data': df.to_dict('records'),
                    'index': df.index.astype(str).tolist()
                }
                await cache.set(cache_key, cache_data, settings.CACHE_TTL_MARKET_DATA)

            return df

        except Exception as e:
            logger.error(f"Error fetching data for {normalized_ticker}: {e}")
            return None

    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add comprehensive technical indicators.
        Optimized to handle both stocks and indices.
        """
        if len(df) < 200:
            logger.warning(f"Only {len(df)} rows - some indicators may be incomplete")

        # Momentum Indicators
        df['RSI'] = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()

        # Stochastic Oscillator
        stoch = ta.momentum.StochasticOscillator(df['High'], df['Low'], df['Close'])
        df['Stoch_K'] = stoch.stoch()
        df['Stoch_D'] = stoch.stoch_signal()

        # MACD
        macd = ta.trend.MACD(df['Close'])
        df['MACD'] = macd.macd()
        df['MACD_signal'] = macd.macd_signal()
        df['MACD_hist'] = macd.macd_diff()

        # Moving Averages
        df['SMA_20'] = ta.trend.SMAIndicator(df['Close'], window=20).sma_indicator()
        df['SMA_50'] = ta.trend.SMAIndicator(df['Close'], window=50).sma_indicator()
        df['SMA_200'] = ta.trend.SMAIndicator(df['Close'], window=200).sma_indicator()
        df['EMA_12'] = ta.trend.EMAIndicator(df['Close'], window=12).ema_indicator()
        df['EMA_26'] = ta.trend.EMAIndicator(df['Close'], window=26).ema_indicator()

        # Bollinger Bands (critical for volatility analysis)
        bollinger = ta.volatility.BollingerBands(df['Close'])
        df['BB_High'] = bollinger.bollinger_hband()
        df['BB_Mid'] = bollinger.bollinger_mavg()
        df['BB_Low'] = bollinger.bollinger_lband()
        df['BB_Width'] = bollinger.bollinger_wband()

        # ATR (Average True Range)
        df['ATR'] = ta.volatility.AverageTrueRange(
            df['High'], df['Low'], df['Close']
        ).average_true_range()

        # Volume indicators (if volume exists)
        if 'Volume' in df.columns and df['Volume'].sum() > 0:
            df['OBV'] = ta.volume.OnBalanceVolumeIndicator(
                df['Close'], df['Volume']
            ).on_balance_volume()
        else:
            df['OBV'] = None

        # ADX (Average Directional Index)
        adx = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close'])
        df['ADX'] = adx.adx()
        df['ADX_Pos'] = adx.adx_pos()
        df['ADX_Neg'] = adx.adx_neg()

        return df

    # High-quality news sources (prioritized)
    TRUSTED_SOURCES = {
        'Reuters', 'Bloomberg', 'The Wall Street Journal', 'Financial Times',
        'CNBC', 'MarketWatch', 'Barron\'s', 'Seeking Alpha', 'The Motley Fool',
        'Yahoo Finance', 'Benzinga', 'Zacks', 'InvestorPlace'
    }

    def _calculate_sentiment_score(self, title: str) -> float:
        """
        Calculate basic sentiment score from news title.
        Returns: -1.0 (very negative) to +1.0 (very positive)
        """
        title_lower = title.lower()

        # Positive keywords
        positive_words = [
            'surge', 'soar', 'jump', 'rally', 'gain', 'rise', 'up', 'high', 'record',
            'beat', 'exceed', 'strong', 'growth', 'profit', 'upgrade', 'bullish',
            'breakthrough', 'partnership', 'acquisition', 'innovation', 'success',
            'positive', 'outperform', 'boost', 'momentum', 'advance'
        ]

        # Negative keywords
        negative_words = [
            'plunge', 'crash', 'fall', 'drop', 'decline', 'down', 'low', 'loss',
            'miss', 'weak', 'concern', 'worry', 'risk', 'downgrade', 'bearish',
            'warning', 'cut', 'slash', 'investigation', 'lawsuit', 'failure',
            'negative', 'underperform', 'tumble', 'slump', 'retreat'
        ]

        positive_count = sum(1 for word in positive_words if word in title_lower)
        negative_count = sum(1 for word in negative_words if word in title_lower)

        # Calculate score
        total = positive_count + negative_count
        if total == 0:
            return 0.0  # Neutral

        score = (positive_count - negative_count) / total
        return max(-1.0, min(1.0, score))

    def _calculate_time_decay_weight(self, published_timestamp: int) -> float:
        """
        Calculate time decay weight for news relevance.
        Recent news (< 24h) = 1.0, older news decays exponentially.
        """
        if not published_timestamp:
            return 0.5  # Unknown time = medium weight

        try:
            published_dt = datetime.fromtimestamp(published_timestamp)
            age_hours = (datetime.now() - published_dt).total_seconds() / 3600

            # Exponential decay: weight = e^(-age/24)
            # News < 24h old: weight ≈ 1.0
            # News 48h old: weight ≈ 0.37
            # News 72h old: weight ≈ 0.14
            import math
            weight = math.exp(-age_hours / 24)
            return max(0.1, min(1.0, weight))  # Clamp between 0.1 and 1.0
        except:
            return 0.5

    async def get_news(self, ticker: str, use_cache: bool = True) -> List[Dict]:
        """
        Fetch latest news with enhanced sentiment analysis, source quality filtering,
        and time decay weighting.
        TTL: 10 minutes (news doesn't change that fast)

        Args:
            ticker: Stock/Index symbol
            use_cache: Whether to use cache

        Returns:
            List of news articles with sentiment scores and relevance weights
        """
        normalized_ticker = self._normalize_ticker(ticker)
        cache_key = f"news:{normalized_ticker}"

        # Try cache first
        if use_cache:
            cached = await cache.get(cache_key)
            if cached:
                logger.debug(f"Cache HIT: news for {normalized_ticker}")
                return cached

        logger.debug(f"Cache MISS: news for {normalized_ticker}")

        news_list = []
        try:
            stock = yf.Ticker(normalized_ticker)
            raw_news = stock.news

            if raw_news and isinstance(raw_news, list):
                for n in raw_news[:15]:  # Fetch more, filter later
                    if not isinstance(n, dict):
                        continue

                    publisher = n.get('publisher', 'Unknown')
                    title = n.get('title', 'No title')
                    published_time = n.get('providerPublishTime', 0)

                    # Calculate sentiment score
                    sentiment_score = self._calculate_sentiment_score(title)

                    # Calculate time decay weight
                    time_weight = self._calculate_time_decay_weight(published_time)

                    # Source quality score (1.0 for trusted, 0.7 for others)
                    source_quality = 1.0 if publisher in self.TRUSTED_SOURCES else 0.7

                    # Overall relevance score (combines time and source quality)
                    relevance_score = time_weight * source_quality

                    news_item = {
                        'title': title,
                        'publisher': publisher,
                        'link': n.get('link', ''),
                        'published': datetime.fromtimestamp(published_time).isoformat() if published_time else None,
                        'sentiment_score': round(sentiment_score, 2),
                        'time_weight': round(time_weight, 2),
                        'source_quality': source_quality,
                        'relevance_score': round(relevance_score, 2),
                        'summary': n.get('summary', '')[:200] if n.get('summary') else ''  # First 200 chars
                    }

                    news_list.append(news_item)

                # Sort by relevance score (most relevant first)
                news_list.sort(key=lambda x: x['relevance_score'], reverse=True)

                # Keep top 10 most relevant
                news_list = news_list[:10]

            # Cache for 10 minutes
            if use_cache:
                await cache.set(cache_key, news_list, settings.CACHE_TTL_NEWS)

        except Exception as e:
            logger.debug(f"News fetch failed for {normalized_ticker}: {e}")

        return news_list

    async def get_realtime_quote(self, ticker: str) -> Optional[float]:
        """
        Get current price with 1-minute cache.
        Critical for real-time trading decisions.

        Args:
            ticker: Stock/Index symbol

        Returns:
            Current price or None
        """
        normalized_ticker = self._normalize_ticker(ticker)
        cache_key = f"quote:{normalized_ticker}"

        # Try cache (1 min TTL for quotes)
        cached = await cache.get(cache_key)
        if cached:
            return cached

        try:
            stock = yf.Ticker(normalized_ticker)
            info = stock.info
            price = info.get('currentPrice') or info.get('regularMarketPrice')

            if price:
                # Cache for 1 minute only
                await cache.set(cache_key, price, settings.CACHE_TTL_QUOTE)
                return float(price)

        except Exception as e:
            logger.error(f"Error fetching quote for {normalized_ticker}: {e}")

        return None

    async def get_market_news(self, use_cache: bool = True) -> List[Dict]:
        """
        Fetch market-wide news covering macroeconomic events, Fed decisions,
        geopolitical events, and major corporate catalysts.

        Checks major market indices and economic tickers for broad market sentiment.
        TTL: 15 minutes (market-wide news changes less frequently)

        Args:
            use_cache: Whether to use cache

        Returns:
            List of market-moving news with sentiment and categorization
        """
        cache_key = "market_news:broad"

        # Try cache first
        if use_cache:
            cached = await cache.get(cache_key)
            if cached:
                logger.debug("Cache HIT: market-wide news")
                return cached

        logger.debug("Cache MISS: market-wide news - fetching")

        # Fetch news from major market indices and economic indicators
        market_tickers = ['^GSPC', '^DJI', '^IXIC', '^VIX']  # S&P 500, Dow, NASDAQ, VIX
        all_news = []

        try:
            for ticker_symbol in market_tickers:
                try:
                    stock = yf.Ticker(ticker_symbol)
                    raw_news = stock.news

                    if raw_news and isinstance(raw_news, list):
                        for n in raw_news[:10]:  # Top 10 from each index
                            if not isinstance(n, dict):
                                continue

                            title = n.get('title', '')
                            publisher = n.get('publisher', 'Unknown')
                            published_time = n.get('providerPublishTime', 0)

                            # Categorize news type based on keywords
                            category = self._categorize_market_news(title)

                            # Calculate sentiment
                            sentiment_score = self._calculate_sentiment_score(title)

                            # Time decay weight
                            time_weight = self._calculate_time_decay_weight(published_time)

                            # Source quality
                            source_quality = 1.0 if publisher in self.TRUSTED_SOURCES else 0.7

                            # Overall relevance (boost for high-impact categories)
                            impact_multiplier = 1.5 if category in ['Fed/Central Bank', 'Macro Data'] else 1.0
                            relevance_score = time_weight * source_quality * impact_multiplier

                            news_item = {
                                'title': title,
                                'publisher': publisher,
                                'link': n.get('link', ''),
                                'published': datetime.fromtimestamp(published_time).isoformat() if published_time else None,
                                'sentiment_score': round(sentiment_score, 2),
                                'category': category,
                                'relevance_score': round(relevance_score, 2),
                                'summary': n.get('summary', '')[:200] if n.get('summary') else ''
                            }

                            all_news.append(news_item)

                except Exception as e:
                    logger.debug(f"Failed to fetch news from {ticker_symbol}: {e}")
                    continue

            # Remove duplicates (same title)
            seen_titles = set()
            unique_news = []
            for item in all_news:
                title_lower = item['title'].lower()
                if title_lower not in seen_titles:
                    seen_titles.add(title_lower)
                    unique_news.append(item)

            # Sort by relevance score
            unique_news.sort(key=lambda x: x['relevance_score'], reverse=True)

            # Keep top 15 most relevant market news
            market_news = unique_news[:15]

            # Cache for 15 minutes
            if use_cache and market_news:
                await cache.set(cache_key, market_news, 900)  # 15 min TTL

            return market_news

        except Exception as e:
            logger.error(f"Error fetching market-wide news: {e}")
            return []

    def _categorize_market_news(self, title: str) -> str:
        """
        Categorize news into market-moving event types.

        Returns category: Fed/Central Bank, Macro Data, Corporate Catalyst,
                         Geopolitical, or General Market
        """
        title_lower = title.lower()

        # Fed/Central Bank keywords
        fed_keywords = ['fed', 'federal reserve', 'fomc', 'powell', 'interest rate',
                       'rate decision', 'central bank', 'monetary policy', 'rate cut', 'rate hike']
        if any(kw in title_lower for kw in fed_keywords):
            return 'Fed/Central Bank'

        # Macroeconomic data keywords
        macro_keywords = ['jobs report', 'unemployment', 'nonfarm payroll', 'nfp', 'cpi',
                         'inflation', 'ppi', 'gdp', 'retail sales', 'consumer', 'pce',
                         'housing starts', 'jobless claims', 'economic data']
        if any(kw in title_lower for kw in macro_keywords):
            return 'Macro Data'

        # Corporate catalyst keywords
        corporate_keywords = ['earnings', 'guidance', 'fda approval', 'merger', 'acquisition',
                             'm&a', 'buyout', 'ipo', 'analyst upgrade', 'analyst downgrade',
                             'revenue', 'profit', 'eps', 'miss', 'beat']
        if any(kw in title_lower for kw in corporate_keywords):
            return 'Corporate Catalyst'

        # Geopolitical keywords
        geo_keywords = ['china', 'russia', 'war', 'tariff', 'trade war', 'sanction',
                       'geopolit', 'military', 'conflict', 'treaty', 'trade deal',
                       'regulation', 'antitrust', 'investigation']
        if any(kw in title_lower for kw in geo_keywords):
            return 'Geopolitical'

        return 'General Market'

    async def get_social_sentiment(self, ticker: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Fetch social media sentiment and buzz score for a ticker.

        Returns sentiment metrics with contrarian analysis:
        - Extreme bullish sentiment (90th+ percentile) = potential sell signal
        - Moderate bullish sentiment = healthy buy signal
        - Low buzz = under-the-radar opportunity

        TTL: 30 minutes (social sentiment changes slower than price)

        Args:
            ticker: Stock symbol
            use_cache: Whether to use cache

        Returns:
            Dict with sentiment_score, buzz_score, percentile, signal
        """
        normalized_ticker = self._normalize_ticker(ticker)
        cache_key = f"social_sentiment:{normalized_ticker}"

        # Try cache first
        if use_cache:
            cached = await cache.get(cache_key)
            if cached:
                logger.debug(f"Cache HIT: social sentiment for {normalized_ticker}")
                return cached

        logger.debug(f"Cache MISS: social sentiment for {normalized_ticker}")

        try:
            # Calculate buzz and sentiment from recent news volume and sentiment
            news = await self.get_news(ticker, use_cache=False)

            if not news or len(news) == 0:
                # No data available
                result = {
                    'sentiment_score': 0.0,
                    'buzz_score': 0.0,
                    'percentile': 50,
                    'signal': 'neutral',
                    'confidence': 'low',
                    'source': 'insufficient_data'
                }
                if use_cache:
                    await cache.set(cache_key, result, 1800)  # 30 min
                return result

            # Calculate sentiment from news (weighted by recency and source quality)
            total_weighted_sentiment = 0
            total_weight = 0
            recent_news_count = 0

            for article in news[:15]:  # Top 15 most relevant
                sentiment = article.get('sentiment_score', 0)
                relevance = article.get('relevance_score', 1.0)

                # Extra weight for very recent news (< 24h)
                time_weight = article.get('time_weight', 0.5)
                recency_multiplier = 2.0 if time_weight > 0.7 else 1.0

                if time_weight > 0.5:  # Recent news
                    recent_news_count += 1

                weight = relevance * recency_multiplier
                total_weighted_sentiment += sentiment * weight
                total_weight += weight

            # Calculate average sentiment (-1 to +1)
            avg_sentiment = total_weighted_sentiment / total_weight if total_weight > 0 else 0.0

            # Calculate buzz score (0-100) based on news volume and recency
            # High buzz = lots of recent news coverage
            max_buzz_threshold = 20  # 20+ recent articles = max buzz
            buzz_score = min(100, (recent_news_count / max_buzz_threshold) * 100)

            # Normalize sentiment to 0-100 scale for percentile calculation
            # -1.0 sentiment = 0 percentile, 0.0 = 50 percentile, +1.0 = 100 percentile
            sentiment_percentile = int((avg_sentiment + 1.0) / 2.0 * 100)

            # CONTRARIAN SIGNAL LOGIC
            # Extreme bullish sentiment (90th+ percentile) = SELL SIGNAL
            # Moderate bullish (60-89 percentile) = BUY SIGNAL
            # Neutral (40-59 percentile) = NEUTRAL
            # Bearish (below 40 percentile) = CONTRARIAN BUY OPPORTUNITY

            if sentiment_percentile >= 90 and buzz_score >= 60:
                signal = 'contrarian_sell'  # Peak euphoria - retail top
                confidence = 'high'
            elif sentiment_percentile >= 90:
                signal = 'extreme_bullish'  # Very bullish but low buzz
                confidence = 'medium'
            elif sentiment_percentile >= 70 and buzz_score >= 40:
                signal = 'bullish'  # Healthy bullish momentum
                confidence = 'high'
            elif sentiment_percentile >= 60:
                signal = 'moderately_bullish'
                confidence = 'medium'
            elif sentiment_percentile >= 40:
                signal = 'neutral'
                confidence = 'medium'
            elif sentiment_percentile >= 20:
                signal = 'moderately_bearish'
                confidence = 'medium'
            elif buzz_score >= 60:
                signal = 'contrarian_buy'  # High buzz but bearish = potential bottom
                confidence = 'medium'
            else:
                signal = 'bearish'
                confidence = 'low'

            result = {
                'sentiment_score': round(avg_sentiment, 2),  # -1 to +1
                'buzz_score': round(buzz_score, 1),  # 0-100
                'percentile': sentiment_percentile,  # 0-100
                'signal': signal,
                'confidence': confidence,
                'recent_articles': recent_news_count,
                'source': 'news_analysis'
            }

            # Cache for 30 minutes
            if use_cache:
                await cache.set(cache_key, result, 1800)

            return result

        except Exception as e:
            logger.debug(f"Social sentiment fetch failed for {normalized_ticker}: {e}")
            # Return neutral on error
            result = {
                'sentiment_score': 0.0,
                'buzz_score': 0.0,
                'percentile': 50,
                'signal': 'neutral',
                'confidence': 'low',
                'source': 'error'
            }
            return result

    async def get_stocks_by_screener(
        self,
        screener_type: str = 'most_actives',
        limit: int = 10
    ) -> List[str]:
        """
        Fetch stocks using Yahoo Finance screener.
        Returns tickers for analysis.

        Args:
            screener_type: Type of screener
            limit: Number of results

        Returns:
            List of ticker symbols
        """
        cache_key = f"screener:{screener_type}:{limit}"

        # Cache screener results for 5 minutes
        cached = await cache.get(cache_key)
        if cached:
            return cached

        screener_endpoints = {
            'most_actives': 'most_actives',
            'day_gainers': 'day_gainers',
            'day_losers': 'day_losers',
            'most_shorted': 'most_shorted_stocks',
            'growth_tech': 'growth_technology_stocks',
            'trending_tickers': 'trending_tickers'
        }

        endpoint = screener_endpoints.get(screener_type, 'most_actives')

        try:
            import requests
            url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
            params = {
                'formatted': 'false',
                'scrIds': endpoint,
                'count': limit
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }

            response = requests.get(url, params=params, headers=headers, timeout=5)

            if response.status_code == 200:
                data = response.json()
                tickers = []

                if 'finance' in data and 'result' in data['finance']:
                    results = data['finance']['result']
                    if results and len(results) > 0:
                        quotes = results[0].get('quotes', [])
                        for quote in quotes:
                            symbol = quote.get('symbol')
                            # Filter out invalid/problematic tickers
                            if symbol and self._is_valid_ticker(symbol):
                                tickers.append(symbol)
                                if len(tickers) >= limit:
                                    break

                if tickers:
                    await cache.set(cache_key, tickers, settings.CACHE_TTL_MARKET_DATA)
                    return tickers

        except Exception as e:
            logger.error(f"Screener fetch failed: {e}")

        # Fallback to curated list
        fallback = ['AAPL', 'TSLA', 'NVDA', 'AMD', 'AMZN', 'MSFT', 'GOOGL', 'META', 'NFLX', 'SPY'][:limit]
        await cache.set(cache_key, fallback, settings.CACHE_TTL_MARKET_DATA)
        return fallback
