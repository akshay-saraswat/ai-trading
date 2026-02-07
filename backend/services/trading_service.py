"""
TradingService - Core business logic for trading operations.

This service is completely decoupled from FastAPI and can be used in:
- Web API (FastAPI)
- CLI tools
- Telegram bots
- Scheduled tasks (cron jobs)
- Testing

ARCHITECTURE:
- Singleton pattern ensures one global instance
- Background monitoring task runs continuously without blocking
- All blocking Robinhood API calls use asyncio.to_thread() to avoid event loop blocking

POSITION MONITORING:
- Started automatically on Robinhood login
- Runs in background checking all positions every POSITION_CHECK_INTERVAL seconds
- Handles take profit/stop loss exits automatically
- NEVER blocks (unlike the deprecated monitor_position() in trader.py)

CONCURRENCY:
- Supports unlimited concurrent users and positions
- Monitoring runs independently in background task
- Thread pool used only for unavoidable blocking Robinhood API calls
"""
import asyncio
import logging
from typing import Optional, Dict
from datetime import datetime

from ..config import settings
from ..cache import cache
from ..database import db
from ..market_data import MarketData
from ..trader import Trader
from ..market_schedule import MarketSchedule

logger = logging.getLogger(__name__)


class TradingService:
    """
    Centralized trading service with async position monitoring.

    Use TradingService.get_instance() to get the singleton instance.
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        """Get or create singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        logger.info("🚀 Initializing Trading Service v2...")
        self.md = MarketData()
        self.trader = Trader()
        self.market_schedule = MarketSchedule()
        self.login_state = {"status": "idle", "message": ""}

        # Monitoring state
        self.monitoring_task: Optional[asyncio.Task] = None
        self.position_settings: Dict[str, Dict] = {}  # {option_id: {tp, sl}}

    async def start(self):
        """
        Start services - connect to cache and database.

        Call this during application startup (e.g., in FastAPI lifespan).
        """
        await cache.connect()
        await db.connect()

        # Load saved settings from database and apply to runtime config
        await self._load_settings_from_database()

        # NOTE: Auto-login disabled - using web-based authentication instead
        # Users now login through the web interface
        # if settings.ROBINHOOD_USERNAME and settings.ROBINHOOD_PASSWORD:
        #     await self._async_login()

        # Start background position monitoring
        if not self.monitoring_task or self.monitoring_task.done():
            self.monitoring_task = asyncio.create_task(self._monitor_positions_loop())
            logger.info(f"✅ Position monitoring started (checking every {settings.POSITION_CHECK_INTERVAL} seconds)")

        logger.info("✅ Trading service started (login via web interface)")

    async def _load_settings_from_database(self):
        """
        Load saved settings from database and update runtime configuration.
        This ensures settings persist across server restarts.
        """
        try:
            settings_data = await db.get_settings()

            if settings_data:
                logger.info("Loading saved settings from database...")

                # Update runtime settings with saved values
                risk = settings_data.get('riskManagement', {})

                if 'default_take_profit' in risk:
                    settings.DEFAULT_TAKE_PROFIT = risk['default_take_profit'] / 100.0
                    logger.info(f"  DEFAULT_TAKE_PROFIT = {settings.DEFAULT_TAKE_PROFIT:.2%}")

                if 'default_stop_loss' in risk:
                    settings.DEFAULT_STOP_LOSS = risk['default_stop_loss'] / 100.0
                    logger.info(f"  DEFAULT_STOP_LOSS = {settings.DEFAULT_STOP_LOSS:.2%}")

                if 'max_position_size' in risk:
                    settings.MAX_POSITION_SIZE = float(risk['max_position_size'])
                    logger.info(f"  MAX_POSITION_SIZE = ${settings.MAX_POSITION_SIZE:,.2f}")

                if 'skip_market_schedule_check' in risk:
                    settings.SKIP_MARKET_SCHEDULE_CHECK = bool(risk['skip_market_schedule_check'])
                    logger.info(f"  SKIP_MARKET_SCHEDULE_CHECK = {settings.SKIP_MARKET_SCHEDULE_CHECK}")

                if 'block_first_hour_trading' in risk:
                    settings.BLOCK_FIRST_HOUR_TRADING = bool(risk['block_first_hour_trading'])
                    logger.info(f"  BLOCK_FIRST_HOUR_TRADING = {settings.BLOCK_FIRST_HOUR_TRADING}")

                logger.info("✅ Settings loaded successfully from database")
            else:
                logger.info("No saved settings found - using defaults from config.py")

        except Exception as e:
            logger.warning(f"Failed to load settings from database: {e}")
            logger.info("Using default settings from config.py")

    async def shutdown(self):
        """
        Cleanup on shutdown - disconnect from services.

        Call this during application shutdown (e.g., in FastAPI lifespan).
        """
        if self.monitoring_task:
            self.monitoring_task.cancel()
        await cache.disconnect()
        await db.disconnect()

    async def _monitor_positions_loop(self):
        """
        Async position monitoring loop - non-blocking background task.

        Runs continuously checking all open positions with dynamic interval:
        - During market hours: POSITION_CHECK_INTERVAL seconds (default 30s)
        - After market close: 1 hour (3600s) to reduce unnecessary API calls

        Uses asyncio.to_thread() to avoid blocking the event loop when calling
        synchronous Robinhood API methods.

        This is the ONLY position monitoring mechanism - the blocking monitor_position()
        method in trader.py is deprecated and will raise an error if called.
        """
        logger.info("🔍 Starting async position monitoring loop")
        last_market_status = None  # Track to log only on status change

        while True:
            try:
                if not self.trader.is_logged_in():
                    logger.debug("Not logged in, waiting 60s before retry")
                    await asyncio.sleep(60)
                    continue

                # Check if market is open for dynamic interval adjustment
                market_open = self.market_schedule.is_market_open_for_new_trades()

                # Log market status changes
                if market_open != last_market_status:
                    if market_open:
                        logger.info(f"📈 Market is open - checking positions every {settings.POSITION_CHECK_INTERVAL}s")
                    else:
                        logger.info("🌙 Market is closed - checking positions every 1 hour")
                    last_market_status = market_open

                # Determine check interval based on market status
                check_interval = settings.POSITION_CHECK_INTERVAL if market_open else 3600  # 1 hour when closed

                # Get positions from Robinhood (offload to thread pool to avoid blocking)
                # asyncio.to_thread() is cleaner than run_in_executor for simple blocking calls
                positions = await asyncio.to_thread(
                    self.trader.get_all_open_option_positions
                )

                # Check each position for TP/SL
                positions_checked = 0
                for pos in positions:
                    option_id = pos.get('option_id')
                    if not option_id:
                        continue

                    positions_checked += 1

                    # Get TP/SL settings from DB
                    db_pos = await db.get_position(option_id)
                    if not db_pos:
                        # Load from memory or use defaults
                        settings_dict = self.position_settings.get(option_id, {
                            'take_profit': settings.DEFAULT_TAKE_PROFIT,
                            'stop_loss': settings.DEFAULT_STOP_LOSS
                        })
                    else:
                        settings_dict = {
                            'take_profit': db_pos['take_profit'],
                            'stop_loss': db_pos['stop_loss']
                        }

                    take_profit = settings_dict.get('take_profit')
                    stop_loss = settings_dict.get('stop_loss')

                    if not take_profit and not stop_loss:
                        continue

                    # Check P&L
                    pnl_percent = pos.get('pnl_percent', 0) / 100.0

                    # Take Profit hit
                    if take_profit and pnl_percent >= take_profit:
                        logger.info(f"🎯 TP hit: {pos['ticker']} at {pnl_percent*100:.2f}%")
                        await self._sell_position(pos, "Take Profit")
                        continue

                    # Stop Loss hit
                    if stop_loss and pnl_percent <= -stop_loss:
                        logger.info(f"🛑 SL hit: {pos['ticker']} at {pnl_percent*100:.2f}%")
                        await self._sell_position(pos, "Stop Loss")
                        continue

                # Log monitoring cycle completion
                if positions_checked > 0:
                    logger.debug(f"✓ Checked {positions_checked} positions, no exits triggered")

                # Sleep before next check with dynamic interval (non-blocking!)
                await asyncio.sleep(check_interval)

            except asyncio.CancelledError:
                logger.info("Monitoring cancelled")
                break
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    async def _sell_position(self, position: Dict, reason: str):
        """
        Async wrapper to sell a position without blocking the event loop.

        Uses asyncio.to_thread() to offload the blocking Robinhood API call
        to a thread pool worker, allowing other requests to continue processing.
        """
        try:
            ticker = position['ticker']
            option_id = position['option_id']

            logger.info(f"💰 Selling {ticker} due to {reason}")

            trade_details = {
                'option_id': option_id,
                'quantity': position['contracts'],
                'entry_price': position['entry_price']
            }

            # Run blocking sell in thread pool (non-blocking)
            await asyncio.to_thread(
                self.trader.sell_option,
                trade_details
            )

            # Update database
            await db.close_position(
                position_id=option_id,
                exit_price=position.get('current_price', 0),
                reason=reason
            )

            # Remove from memory settings
            if option_id in self.position_settings:
                del self.position_settings[option_id]

        except Exception as e:
            logger.error(f"Error selling position: {e}")


# Global singleton instance
trading_service = TradingService.get_instance()
