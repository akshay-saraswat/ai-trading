"""
Test script for the intelligent fallback data source system.
Demonstrates how the system automatically switches between data sources.

Run with: python -m backend.test_fallback_system
"""
import asyncio
import logging
import sys
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import our data source system
from backend.data_sources import (
    DataSourceOrchestrator,
    RateLimitError,
    YFinanceDataSource,
    AlphaVantageDataSource,
    FinnhubDataSource
)
from backend.config import settings


async def test_historical_data(orchestrator: DataSourceOrchestrator, ticker: str):
    """Test historical data fetching with fallback"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing Historical Data for {ticker}")
    logger.info(f"{'='*60}")

    try:
        df = await orchestrator.get_historical_data(ticker)
        if df is not None:
            logger.info(f"✓ Successfully fetched {len(df)} days of data")
            logger.info(f"  Columns: {list(df.columns)}")
            logger.info(f"  Date range: {df.index[0]} to {df.index[-1]}")
            logger.info(f"  Latest close: ${df['Close'].iloc[-1]:.2f}")
            return True
        else:
            logger.error(f"✗ Failed to fetch data for {ticker}")
            return False
    except Exception as e:
        logger.error(f"✗ Error: {e}")
        return False


async def test_quote(orchestrator: DataSourceOrchestrator, ticker: str):
    """Test real-time quote fetching with fallback"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing Real-time Quote for {ticker}")
    logger.info(f"{'='*60}")

    try:
        price = await orchestrator.get_quote(ticker)
        if price is not None:
            logger.info(f"✓ Successfully fetched quote: ${price:.2f}")
            return True
        else:
            logger.error(f"✗ Failed to fetch quote for {ticker}")
            return False
    except Exception as e:
        logger.error(f"✗ Error: {e}")
        return False


async def test_news(orchestrator: DataSourceOrchestrator, ticker: str):
    """Test news fetching with fallback"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing News for {ticker}")
    logger.info(f"{'='*60}")

    try:
        news = await orchestrator.get_news(ticker)
        if news:
            logger.info(f"✓ Successfully fetched {len(news)} articles")
            for i, article in enumerate(news[:3], 1):
                logger.info(f"  {i}. {article.get('title', 'No title')[:80]}")
            return True
        else:
            logger.warning(f"⚠ No news available for {ticker}")
            return True  # No news is not a failure
    except Exception as e:
        logger.error(f"✗ Error: {e}")
        return False


async def test_circuit_breaker():
    """Test circuit breaker pattern by simulating failures"""
    logger.info(f"\n{'='*60}")
    logger.info("Testing Circuit Breaker Pattern")
    logger.info(f"{'='*60}")

    # Create a simple orchestrator
    orchestrator = DataSourceOrchestrator()

    # Check initial state
    status = orchestrator.get_status()
    logger.info(f"Initial status:")
    for source_name, source_status in status.items():
        logger.info(f"  {source_name}: available={source_status['available']}, "
                   f"circuit_open={source_status['circuit_open']}")

    # Simulate using an invalid ticker to trigger failures
    invalid_ticker = "INVALID_TICKER_XYZ123"

    logger.info(f"\nAttempting to fetch data for invalid ticker '{invalid_ticker}'...")
    logger.info("This will trigger failures and potentially open circuit breakers...")

    for attempt in range(5):
        logger.info(f"\n--- Attempt {attempt + 1} ---")
        try:
            await orchestrator.get_historical_data(invalid_ticker)
        except Exception as e:
            logger.info(f"Expected failure: {type(e).__name__}")

        # Check status after each attempt
        status = orchestrator.get_status()
        for source_name, source_status in status.items():
            if source_status['circuit_open']:
                logger.warning(f"  ⚠ {source_name}: Circuit breaker OPENED "
                             f"(failures: {source_status['failure_count']})")
            elif source_status['failure_count'] > 0:
                logger.info(f"  {source_name}: failures={source_status['failure_count']}, "
                          f"circuit still closed")

    logger.info("\nCircuit breaker test completed")


async def display_status(orchestrator: DataSourceOrchestrator):
    """Display comprehensive status of all data sources"""
    logger.info(f"\n{'='*60}")
    logger.info("Data Source Status")
    logger.info(f"{'='*60}")

    status = orchestrator.get_status()

    for source_name, source_status in status.items():
        logger.info(f"\n{source_name}:")
        logger.info(f"  Available: {source_status['available']}")
        logger.info(f"  Circuit Open: {source_status['circuit_open']}")
        logger.info(f"  Failure Count: {source_status['failure_count']}")
        logger.info(f"  Success Count: {source_status['success_count']}")
        if source_status['last_failure']:
            logger.info(f"  Last Failure: {source_status['last_failure']}")


async def run_comprehensive_test():
    """Run comprehensive tests of the fallback system"""
    logger.info("="*60)
    logger.info("Intelligent Fallback Data Source System - Comprehensive Test")
    logger.info("="*60)

    # Check API keys
    logger.info(f"\nAPI Key Configuration:")
    logger.info(f"  AlphaVantage: {'✓ Configured' if settings.ALPHA_VANTAGE_API_KEY else '✗ Not configured'}")
    logger.info(f"  Finnhub: {'✓ Configured' if settings.FINNHUB_API_KEY else '✗ Not configured'}")

    # Create orchestrator
    orchestrator = DataSourceOrchestrator(
        alpha_vantage_key=settings.ALPHA_VANTAGE_API_KEY,
        finnhub_key=settings.FINNHUB_API_KEY
    )

    # Test tickers
    test_tickers = ['AAPL', 'TSLA', 'MSFT']

    results = {
        'historical': [],
        'quote': [],
        'news': []
    }

    # Test each ticker
    for ticker in test_tickers:
        # Test historical data
        success = await test_historical_data(orchestrator, ticker)
        results['historical'].append((ticker, success))

        # Small delay between tests
        await asyncio.sleep(1)

        # Test quote
        success = await test_quote(orchestrator, ticker)
        results['quote'].append((ticker, success))

        await asyncio.sleep(1)

        # Test news
        success = await test_news(orchestrator, ticker)
        results['news'].append((ticker, success))

        await asyncio.sleep(1)

    # Display final status
    await display_status(orchestrator)

    # Test circuit breaker (optional)
    # await test_circuit_breaker()

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("Test Summary")
    logger.info(f"{'='*60}")

    for data_type, test_results in results.items():
        successes = sum(1 for _, success in test_results if success)
        total = len(test_results)
        logger.info(f"{data_type.capitalize()}: {successes}/{total} successful")

    logger.info("\nTest completed!")


async def quick_demo():
    """Quick demo showing fallback in action"""
    logger.info("="*60)
    logger.info("Quick Demo: Fallback System")
    logger.info("="*60)

    orchestrator = DataSourceOrchestrator(
        alpha_vantage_key=settings.ALPHA_VANTAGE_API_KEY,
        finnhub_key=settings.FINNHUB_API_KEY
    )

    ticker = "AAPL"

    # Test all three operations
    logger.info(f"\nFetching data for {ticker}...")

    # Historical data
    df = await orchestrator.get_historical_data(ticker)
    if df is not None:
        logger.info(f"✓ Historical: {len(df)} days, latest close: ${df['Close'].iloc[-1]:.2f}")

    # Quote
    quote = await orchestrator.get_quote(ticker)
    if quote:
        logger.info(f"✓ Quote: ${quote:.2f}")

    # News
    news = await orchestrator.get_news(ticker)
    if news:
        logger.info(f"✓ News: {len(news)} articles")
        logger.info(f"  Top: {news[0]['title'][:80]}")

    # Show status
    await display_status(orchestrator)


if __name__ == "__main__":
    # Check if user wants quick demo or full test
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        asyncio.run(quick_demo())
    elif len(sys.argv) > 1 and sys.argv[1] == "--circuit-breaker":
        asyncio.run(test_circuit_breaker())
    else:
        print("\nRunning comprehensive test...")
        print("Use --quick for a quick demo")
        print("Use --circuit-breaker to test circuit breaker pattern\n")
        asyncio.run(run_comprehensive_test())
