"""
HTTP REST API routes for the trading bot.

Handles:
- Health checks
- Authentication (login/logout/session)
- Login status
- Position management (CRUD)
- Insights and ticker analysis
- Option trade placement
"""
import asyncio
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import HTTPException, APIRouter, Header
from pydantic import BaseModel

from .models import Position, UpdateTPSLRequest
from ..services.trading_service import trading_service
from ..analyst import analyst
from ..config import settings
from ..database import db
from ..cache import cache
from ..auth import auth_manager

logger = logging.getLogger(__name__)


# Auth request models
class LoginRequest(BaseModel):
    username: str
    password: str


class MFACheckRequest(BaseModel):
    challenge_id: str

# Create router
router = APIRouter()


# ==========================================
# Authentication Endpoints
# ==========================================

@router.post("/api/auth/login")
async def login(request: LoginRequest):
    """
    Login to Robinhood.
    Returns:
    - {success: true, token: "..."} on success
    - {requires_mfa: true, challenge_id: "..."} if MFA needed
    """
    try:
        result = await auth_manager.login(request.username, request.password)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/auth/mfa/check")
async def check_mfa(request: MFACheckRequest):
    """
    Check if MFA was approved.
    Frontend should poll this endpoint every 2-3 seconds.

    Returns:
    - {success: true, token: "..."} if MFA approved
    - {pending: true, message: "..."} if still waiting
    """
    try:
        result = await auth_manager.complete_mfa(request.challenge_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"MFA check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Logout and invalidate session"""
    if not authorization or not authorization.startswith("Bearer "):
        return {"success": False, "message": "No token provided"}

    token = authorization.replace("Bearer ", "")
    success = auth_manager.logout(token)

    return {"success": success}


@router.get("/api/auth/session")
async def check_session(authorization: Optional[str] = Header(None)):
    """Check if session is valid"""
    if not authorization or not authorization.startswith("Bearer "):
        return {"authenticated": False}

    token = authorization.replace("Bearer ", "")
    authenticated = auth_manager.is_authenticated(token)

    if authenticated:
        session = auth_manager.get_session(token)
        return {
            "authenticated": True,
            "username": session.get('username'),
            "expires_at": session.get('expires_at').isoformat()
        }

    return {"authenticated": False}


# ==========================================
# Health & Status Endpoints
# ==========================================

@router.get("/api/health")
async def health_check():
    """Health check for ALB"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "logged_in": trading_service.trader.logged_in,
        "market_open": trading_service.market_schedule.is_market_open_for_new_trades(),
        "cache_enabled": cache.enabled,
        "db_connected": db.conn is not None
    }


@router.get("/api/login-status")
async def get_login_status():
    """Get Robinhood login status"""
    return {
        "status": trading_service.login_state["status"],
        "message": trading_service.login_state["message"],
        "logged_in": trading_service.trader.logged_in
    }


@router.get("/api/positions")
async def get_positions() -> List[Position]:
    """Get all positions (from DB + live Robinhood sync)"""
    positions = []

    # Get positions from Robinhood
    loop = asyncio.get_event_loop()
    rh_positions = await loop.run_in_executor(
        None,
        trading_service.trader.get_all_open_option_positions
    )

    for pos in rh_positions:
        option_id = pos.get('option_id', f"rh_{pos['ticker']}")

        # Get settings from DB or use defaults
        db_pos = await db.get_position(option_id)
        if db_pos:
            tp = db_pos['take_profit']
            sl = db_pos['stop_loss']
        else:
            tp = settings.DEFAULT_TAKE_PROFIT
            sl = settings.DEFAULT_STOP_LOSS

        positions.append(Position(
            position_id=option_id,
            ticker=pos['ticker'],
            decision=pos['decision'],
            entry_price=pos['entry_price'],
            current_price=pos.get('current_price'),
            pct_change=pos.get('pnl_percent') / 100 if pos.get('pnl_percent') else None,
            strike=str(pos['strike']),
            expiration=pos['expiration'],
            contracts=pos['contracts'],
            take_profit=tp,
            stop_loss=sl,
            started_at=None,
            source='robinhood'
        ))

    return positions


@router.put("/api/positions/{position_id}/take-profit")
async def update_take_profit(position_id: str, request: UpdateTPSLRequest):
    """Update take-profit"""
    if request.value < 5 or request.value > 100:
        raise HTTPException(400, "Take-profit must be 5-100%")

    # Update in memory
    if position_id not in trading_service.position_settings:
        trading_service.position_settings[position_id] = {}
    trading_service.position_settings[position_id]['take_profit'] = request.value / 100.0

    # Update in DB
    await db.update_position(position_id, {'take_profit': request.value / 100.0})

    return {"success": True, "message": f"TP updated to {request.value}%"}


@router.put("/api/positions/{position_id}/stop-loss")
async def update_stop_loss(position_id: str, request: UpdateTPSLRequest):
    """Update stop-loss"""
    if request.value < 1 or request.value > 50:
        raise HTTPException(400, "Stop-loss must be 1-50%")

    # Update in memory
    if position_id not in trading_service.position_settings:
        trading_service.position_settings[position_id] = {}
    trading_service.position_settings[position_id]['stop_loss'] = request.value / 100.0

    # Update in DB
    await db.update_position(position_id, {'stop_loss': request.value / 100.0})

    return {"success": True, "message": f"SL updated to {request.value}%"}


@router.delete("/api/positions/{position_id}")
async def close_position(position_id: str):
    """Close position manually"""
    db_pos = await db.get_position(position_id)
    if not db_pos:
        raise HTTPException(404, "Position not found")

    try:
        trade_details = {
            'option_id': position_id,
            'quantity': db_pos['contracts'],
            'entry_price': db_pos['entry_price']
        }

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            trading_service.trader.sell_option,
            trade_details
        )

        await db.close_position(position_id, 0, "Manual close")

        return {"success": True, "message": f"Closed {db_pos['ticker']}"}

    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/api/insights/tickers")
async def get_tickers(screener: str = 'most_actives'):
    """Get ticker list from screener"""
    tickers = await trading_service.md.get_stocks_by_screener(screener, limit=10)
    return {"success": True, "tickers": tickers, "screener": screener}


@router.get("/api/insights/analyze/{ticker}")
async def analyze_ticker_insight(ticker: str):
    """Analyze single ticker with caching"""
    # Fetch data (uses cache automatically)
    df = await trading_service.md.get_stock_data(ticker)
    if df is None or df.empty:
        raise HTTPException(404, f"No data for {ticker}")

    current_price = float(df['Close'].iloc[-1])

    # Get indicators
    indicators = {
        'RSI': float(df['RSI'].iloc[-1]) if 'RSI' in df else None,
        'SMA_50': float(df['SMA_50'].iloc[-1]) if 'SMA_50' in df else None,
        'SMA_200': float(df['SMA_200'].iloc[-1]) if 'SMA_200' in df else None,
        'MACD': float(df['MACD'].iloc[-1]) if 'MACD' in df else None,
        'MACD_signal': float(df['MACD_signal'].iloc[-1]) if 'MACD_signal' in df else None,
    }

    # Get ticker-specific news
    news = await trading_service.md.get_news(ticker)

    # Get market-wide news (Fed, macro, geopolitical)
    market_news = await trading_service.md.get_market_news()

    # Get social sentiment (contrarian signals for extreme sentiment)
    social_sentiment = await trading_service.md.get_social_sentiment(ticker)

    # AI analysis (run in thread pool - calls AWS Bedrock)
    # Let the AI dynamically choose the best strategy
    analysis = await asyncio.to_thread(
        analyst.analyze_ticker,
        ticker, current_price, indicators, news,
        market_news,  # Market-wide context
        social_sentiment  # Social sentiment with contrarian logic
    )

    # Get option recommendation if decision is BUY_CALL or BUY_PUT
    option_data = None
    if analysis['decision'] in ['BUY_CALL', 'BUY_PUT']:
        target_premium_pct = analysis.get('target_premium_pct', 0.95)
        # Find best option (run in thread pool - calls Robinhood API)
        option = await asyncio.to_thread(
            trading_service.trader.find_best_option,
            ticker,
            analysis['decision'],
            settings.MAX_POSITION_SIZE,
            target_premium_pct
        )

        if option:
            market_price = option.get('market_price', 0)
            limit_price = option.get('limit_price', market_price)
            strike = option.get('strike_price', option.get('strike', 0))
            expiration = option.get('expiration_date', option.get('expiration', 'N/A'))

            # Calculate max contracts based on budget
            max_contracts = int(settings.MAX_POSITION_SIZE / (market_price * 100)) if market_price > 0 else 0

            option_data = {
                "option_id": option.get('id'),
                "type": analysis['decision'],
                "strike": strike,
                "expiration": expiration,
                "market_price": market_price,
                "limit_price": limit_price,
                "max_contracts": max_contracts,
                "cost_per_contract": market_price * 100
            }

    return {
        "success": True,
        "insight": {
            "ticker": ticker,
            "current_price": current_price,
            "decision": analysis['decision'],
            "confidence": analysis['confidence'],
            "reasoning": analysis['reasoning'],
            "strategy_used": analysis.get('strategy_used', 'none'),
            "indicators": indicators,
            "option": option_data
        }
    }


@router.post("/api/trade/place-option")
async def place_option_trade(request: dict):
    """
    Place an option trade with specified number of contracts.
    Request body: {
        "option_id": str,
        "ticker": str,
        "decision": "BUY_CALL" or "BUY_PUT",
        "contracts": int,
        "strike": float,
        "expiration": str,
        "limit_price": float
    }
    """
    try:
        # Check if market is open for new trades
        if not trading_service.market_schedule.is_market_open_for_new_trades():
            next_open = trading_service.market_schedule.get_next_market_open()
            time_until = trading_service.market_schedule.get_time_until_market_open()
            return {
                "success": False,
                "message": f"Market is closed. Next open: {next_open.strftime('%A, %B %d at %I:%M %p %Z')} ({time_until})"
            }

        option_id = request.get('option_id')
        ticker = request.get('ticker')
        decision = request.get('decision')
        contracts = int(request.get('contracts', 1))
        strike = float(request.get('strike'))
        expiration = request.get('expiration')
        limit_price = float(request.get('limit_price'))

        if not all([option_id, ticker, decision, contracts > 0]):
            return {
                "success": False,
                "message": "Missing required fields"
            }

        # Construct option object for place_trade
        option = {
            "id": option_id,
            "symbol": ticker,
            "type": "call" if decision == "BUY_CALL" else "put",
            "strike_price": strike,
            "expiration": expiration,
            "market_price": limit_price,
            "limit_price": limit_price
        }

        # Calculate budget based on contracts
        budget = contracts * limit_price * 100

        # Place the trade (run blocking Robinhood API call in thread pool)
        order = await asyncio.to_thread(
            trading_service.trader.place_trade,
            option,
            budget
        )

        if order:
            # Calculate take profit and stop loss
            take_profit = limit_price * (1 + settings.DEFAULT_TAKE_PROFIT)
            stop_loss = limit_price * (1 - settings.DEFAULT_STOP_LOSS)

            # Save to database using create_position
            position_id = order.get('id', f"pos_{ticker}_{datetime.utcnow().timestamp()}")
            await db.create_position({
                "id": position_id,
                "ticker": ticker,
                "decision": decision,
                "option_id": option_id,
                "strike": strike,
                "expiration": expiration,
                "contracts": contracts,
                "entry_price": limit_price,
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "source": "bot"
            })

            return {
                "success": True,
                "message": f"Order placed: {contracts} contract(s) of {ticker} ${strike} {decision}",
                "order_id": position_id,
                "details": {
                    "contracts": contracts,
                    "limit_price": limit_price,
                    "total_cost": limit_price * contracts * 100
                }
            }
        else:
            return {
                "success": False,
                "message": "Failed to place order"
            }

    except Exception as e:
        logger.error(f"Error placing option trade: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }

# ========== SETTINGS ENDPOINTS ==========

@router.get("/api/settings")
async def get_settings():
    """
    Get current application settings.
    Returns settings from database or defaults from config.
    """
    # Get settings from database
    settings_data = await db.get_settings()

    if not settings_data:
        # Return defaults from config
        settings_data = {
            'indicators': {
                'RSI': True,
                'MACD': True,
                'Stochastic': True,
                'SMA_20': True,
                'SMA_50': True,
                'SMA_200': True,
                'EMA_12': True,
                'EMA_26': True,
                'Bollinger_Bands': True,
                'ATR': True,
                'ADX': True,
                'OBV': True,
            },
            'riskManagement': {
                'default_take_profit': settings.DEFAULT_TAKE_PROFIT * 100,  # Convert to percentage
                'default_stop_loss': settings.DEFAULT_STOP_LOSS * 100,
                'max_position_size': settings.MAX_POSITION_SIZE,
                'skip_market_schedule_check': settings.SKIP_MARKET_SCHEDULE_CHECK,
                'block_first_hour_trading': settings.BLOCK_FIRST_HOUR_TRADING,
            }
        }

    return settings_data


@router.put("/api/settings")
async def update_settings(request: dict):
    """
    Update application settings.
    Saves to database and updates runtime config.
    """
    try:
        # Save to database
        await db.save_settings(request)

        # Update runtime settings
        risk = request.get('riskManagement', {})
        if 'default_take_profit' in risk:
            settings.DEFAULT_TAKE_PROFIT = risk['default_take_profit'] / 100.0
        if 'default_stop_loss' in risk:
            settings.DEFAULT_STOP_LOSS = risk['default_stop_loss'] / 100.0
        if 'max_position_size' in risk:
            settings.MAX_POSITION_SIZE = float(risk['max_position_size'])
        if 'skip_market_schedule_check' in risk:
            settings.SKIP_MARKET_SCHEDULE_CHECK = bool(risk['skip_market_schedule_check'])
        if 'block_first_hour_trading' in risk:
            settings.BLOCK_FIRST_HOUR_TRADING = bool(risk['block_first_hour_trading'])

        logger.info(f"Settings updated: MAX_POSITION_SIZE={settings.MAX_POSITION_SIZE}, SKIP_MARKET_SCHEDULE_CHECK={settings.SKIP_MARKET_SCHEDULE_CHECK}, BLOCK_FIRST_HOUR_TRADING={settings.BLOCK_FIRST_HOUR_TRADING}")

        return {
            "success": True,
            "message": "Settings updated successfully"
        }

    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(500, f"Failed to update settings: {str(e)}")
